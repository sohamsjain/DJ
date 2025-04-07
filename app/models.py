from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple, Dict
import calendar
import sqlalchemy as sa
import sqlalchemy.orm as so
import pytz
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login


nytz = pytz.timezone("America/New_York")


class EarningType:
    FIXED = "Fixed"
    VARIABLE = "Variable"


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


class User(UserMixin, db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), unique=True, index=True)
    phone: so.Mapped[str] = so.mapped_column(sa.String(20), index=True)
    password_hash: so.Mapped[str] = so.mapped_column(sa.String(256))
    is_admin: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=False)
    balance: so.Mapped[float] = so.mapped_column(sa.Float, default=0.0)
    earning_type: so.Mapped[str] = so.mapped_column(sa.String(20), default=EarningType.VARIABLE)
    created_at: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True),
                                                       default=lambda: datetime.now(nytz))

    transactions: so.WriteOnlyMapped[List['Transaction']] = so.relationship(
        back_populates='user',
        passive_deletes=True
    )
    approvals: so.WriteOnlyMapped[List['TransactionApproval']] = so.relationship(
        back_populates='admin',
        passive_deletes=True
    )
    days: so.WriteOnlyMapped[List['UserDay']] = so.relationship(
        back_populates='user',
        passive_deletes=True
    )
    user_earnings: so.WriteOnlyMapped[List['UserEarning']] = so.relationship(
        back_populates='user',
        passive_deletes=True
    )
    created_earnings: so.WriteOnlyMapped[List['Earning']] = so.relationship(
        back_populates='created_by',
        passive_deletes=True
    )
    earning_approvals: so.WriteOnlyMapped[List['EarningApproval']] = so.relationship(
        back_populates='admin',
        passive_deletes=True
    )

    def __repr__(self):
        if self.is_admin:
            return '<Admin {}>'.format(self.username)
        return '<User {}>'.format(self.username)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def created_at_est(self):
        return self.created_at.astimezone(nytz).strftime("%b %d %Y %H:%M")

    def initiate_transaction(
            self,
            amount: float,
            type: str,
            proof_of_transaction: Optional[str] = None,
            reference_id: Optional[str] = None,
            description: Optional[str] = None
    ) -> 'Transaction':
        """
        Initiate a new transaction with required proof of transaction.

        Args:
            amount: Transaction amount (must be positive)
            type: Transaction type (deposit/withdrawal)
            proof_of_transaction: Required proof (e.g., receipt image path)
            reference_id: Optional external reference number
            description: Optional transaction description
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")

        if type == TransactionType.WITHDRAWAL and amount > self.balance:
            raise ValueError("Insufficient funds")

        transaction = Transaction(
            user=self,
            amount=amount,
            type=type,
            proof_of_transaction=proof_of_transaction,
            reference_id=reference_id,
            description=description
        )

        if type == TransactionType.EARNINGS:
            unpaid_earnings = self.get_user_earnings(status=UserEarningStatus.SETTLEMENT_PENDING)
            for user_earning in unpaid_earnings:
                user_earning.link_transaction(transaction)

        db.session.add(transaction)
        db.session.commit()
        return transaction

    def get_transactions(
            self,
            transaction_type: Optional[str] = None,
            status: Optional[str] = None,
            limit: Optional[int] = None
    ) -> List[Transaction]:
        """Get user's transaction history"""
        query = self.transactions.select()

        if transaction_type:
            query = query.filter_by(type=transaction_type)
        if status:
            query = query.filter_by(status=status)

        query = query.order_by(Transaction.created_at.desc())

        if limit:
            query = query.limit(limit)

        return db.session.scalars(query).all()

    def get_user_earnings(
            self,
            status: Optional[str] = None,
            limit: Optional[int] = None
    ) -> List[UserEarning]:
        """Get user's earning history"""
        query = self.user_earnings.select()

        if status:
            query = query.filter_by(status=status)

        query = query.order_by(UserEarning.created_at.desc())

        if limit:
            query = query.limit(limit)

        return db.session.scalars(query).all()

    def get_statistics(self) -> Dict:
        """Get statistical summary of user's account"""
        transactions = self.get_transactions(status=TransactionStatus.COMPLETE)
        earnings = self.get_user_earnings()

        total_deposits = sum(t.amount for t in transactions
                             if t.type == TransactionType.DEPOSIT)
        total_withdrawals = sum(t.amount for t in transactions
                                if t.type == TransactionType.WITHDRAWAL)
        earnings_paid = sum(e.total_amount for e in earnings
                            if e.status == UserEarningStatus.COMPLETE)
        earnings_unpaid = sum(e.total_amount for e in earnings
                              if e.status == UserEarningStatus.SETTLEMENT_PENDING)
        total_earnings = earnings_paid + earnings_unpaid

        return {
            'total_deposits': total_deposits,
            'total_withdrawals': total_withdrawals,
            'total_balance': self.balance,
            'earnings_paid': earnings_paid,
            'earnings_unpaid': earnings_unpaid,
            'total_earnings': total_earnings,
        }

    def sync_user_days(self) -> List[UserDay]:
        """
        Sync user days based on completed transactions up to the previous day.
        Creates or updates UserDay records for any missing days.
        """
        # Get the latest user day record
        latest_day = UserDay.query.filter_by(user_id=self.id) \
            .order_by(UserDay.date.desc()) \
            .first()

        # Set start date as either day after latest record or user creation date
        if latest_day:
            start_date = latest_day.date + timedelta(days=1)
        else:
            # Ensure timezone-aware datetime
            start_date = self.created_at.astimezone(nytz).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        # Set end date as yesterday (don't include today as it's not complete)
        end_date = datetime.now(nytz).replace(
            hour=23, minute=59, second=59, microsecond=999999
        ) - timedelta(days=1)

        # Ensure both dates are timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=nytz)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=nytz)

        # If start date is after end date, no syncing needed
        if start_date > end_date:
            return []

        # Get all completed transactions in date range
        transactions = Transaction.query.filter(
            Transaction.user_id == self.id,
            Transaction.status == TransactionStatus.COMPLETE,
            Transaction.completed_at >= start_date,
            Transaction.completed_at <= end_date
        ).order_by(Transaction.completed_at).all()

        # Group transactions by date
        transactions_by_date = {}
        for transaction in transactions:
            # Ensure transaction date is timezone-aware
            completed_at = transaction.completed_at.astimezone(nytz)
            date_key = completed_at.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if date_key not in transactions_by_date:
                transactions_by_date[date_key] = []
            transactions_by_date[date_key].append(transaction)

        # Create or update UserDay records
        new_days = []
        current_date = start_date
        running_balance = latest_day.closing_balance if latest_day else 0.0

        while current_date <= end_date:
            # Process all transactions for the current date
            daily_transactions = transactions_by_date.get(current_date, [])

            for transaction in daily_transactions:
                if transaction.type == TransactionType.DEPOSIT:
                    running_balance += transaction.amount
                elif transaction.type == TransactionType.WITHDRAWAL:
                    running_balance -= transaction.amount
                # Ignore EARNINGS type as it doesn't affect balance

            # Create UserDay record
            day = UserDay(
                user=self,
                date=current_date,
                closing_balance=running_balance
            )
            db.session.add(day)
            new_days.append(day)

            current_date += timedelta(days=1)

        if new_days:
            db.session.commit()

        return new_days

    @property
    def settlements_pending(self):
        amount = 0.0
        user_earnings: list[UserEarning] = db.session.scalars(self.user_earnings.select().filter_by(
            status=UserEarningStatus.SETTLEMENT_PENDING)).all()
        for earning in user_earnings:
            amount += earning.total_amount
        return amount


class TransactionStatus:
    APPROVAL_PENDING = "Approval pending"
    COMPLETE = "Complete"
    REJECTED = "Rejected"


# Add EARNINGS to TransactionType
class TransactionType:
    DEPOSIT = "Deposit"
    WITHDRAWAL = "Withdrawal"
    EARNINGS = "Earnings"  # New type for earnings payments


transaction_userearning = db.Table(
    'transaction_userearning',
    sa.Column('transaction_id', sa.Integer, sa.ForeignKey('transaction.id', ondelete='CASCADE'), primary_key=True),
    sa.Column('user_earning_id', sa.Integer, sa.ForeignKey('user_earning.id', ondelete='CASCADE'), primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=True), default=lambda: datetime.now(nytz))
)


class Transaction(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'), index=True)
    amount: so.Mapped[float] = so.mapped_column(sa.Float)
    type: so.Mapped[str] = so.mapped_column(sa.String(20))
    status: so.Mapped[str] = so.mapped_column(
        sa.String(20),
        default=TransactionStatus.APPROVAL_PENDING
    )

    proof_of_transaction: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255), nullable=True)
    reference_id: so.Mapped[Optional[str]] = so.mapped_column(sa.String(50), nullable=True)
    description: so.Mapped[Optional[str]] = so.mapped_column(sa.Text, nullable=True)

    balance_before: so.Mapped[Optional[float]] = so.mapped_column(sa.Float, nullable=True)
    balance_after: so.Mapped[Optional[float]] = so.mapped_column(sa.Float, nullable=True)
    created_at: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True),
                                                       default=lambda: datetime.now(nytz)
                                                       )
    completed_at: so.Mapped[Optional[datetime]] = so.mapped_column(nullable=True)

    # Relationships
    user: so.Mapped[User] = so.relationship(back_populates='transactions')
    approvals: so.Mapped[List['TransactionApproval']] = so.relationship(
        back_populates='transaction',
        cascade='all, delete-orphan'
    )
    user_earnings: so.Mapped[List['UserEarning']] = so.relationship(
        secondary=transaction_userearning,
        back_populates='transactions'
    )

    def __repr__(self):
        return '<Transaction {}: {} -> {} {}>'.format(
            self.user.username,
            self.type,
            self.amount,
            self.status
        )

    @property
    def created_at_est(self):
        return self.created_at.astimezone(nytz).strftime("%b %d %Y\n%H:%M")

    @property
    def completed_at_est(self):
        return self.completed_at.astimezone(nytz).strftime("%b %d %Y\n%H:%M")

    def update_proof(self, new_proof: Optional[str | None] = None) -> None:
        """Update proof of transaction if still pending"""
        if self.status != TransactionStatus.APPROVAL_PENDING:
            raise ValueError("Cannot update proof for non-pending transactions")
        self.proof_of_transaction = new_proof
        db.session.commit()

    def add_approval(self, admin: User, approved: bool = True, notes: Optional[str] = None) -> 'TransactionApproval':
        """Add admin approval with optional notes"""
        if not admin.is_admin:
            raise ValueError("Only admins can approve transactions")

        if self.status in [TransactionStatus.COMPLETE, TransactionStatus.REJECTED]:
            raise ValueError("Cannot approve completed or rejected transactions")

        if approved and not self.proof_of_transaction:
            raise ValueError("Cannot approve transaction without proof")

        existing_approval = next(
            (a for a in self.approvals if a.admin_id == admin.id),
            None
        )
        if existing_approval:
            raise ValueError("Admin has already processed this transaction")

        approval = TransactionApproval(
            transaction=self,
            admin=admin,
            approved=approved,
            notes=notes
        )
        db.session.add(approval)

        approval_count = sum(1 for a in self.approvals if a.approved)
        rejection_count = sum(1 for a in self.approvals if not a.approved)

        if rejection_count > 0:
            self.status = TransactionStatus.REJECTED
        elif approval_count >= 2:
            self._complete_transaction()

        db.session.commit()
        return approval

    def _complete_transaction(self) -> None:
        """Complete the transaction and update user balance"""
        self.balance_before = self.user.balance

        if self.type == TransactionType.DEPOSIT:
            self.user.balance += self.amount
        elif self.type == TransactionType.WITHDRAWAL:  # Withdrawal
            if self.amount > self.user.balance:
                raise ValueError("Insufficient funds")
            self.user.balance -= self.amount
        elif self.type == TransactionType.EARNINGS:
            for unpaid_earning in self.user_earnings:
                unpaid_earning.status = UserEarningStatus.COMPLETE

        self.balance_after = self.user.balance
        self.status = TransactionStatus.COMPLETE
        self.completed_at = datetime.now(nytz)


class TransactionApproval(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    transaction_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('transaction.id'), index=True)
    admin_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'), index=True)
    approved: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=True)
    notes: so.Mapped[Optional[str]] = so.mapped_column(sa.Text, nullable=True)
    created_at: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True),
                                                       default=lambda: datetime.now(nytz)
                                                       )

    # Relationships
    transaction: so.Mapped[Transaction] = so.relationship(back_populates='approvals')
    admin: so.Mapped[User] = so.relationship(back_populates='approvals')

    @property
    def created_at_est(self):
        return self.created_at.astimezone(nytz).strftime("%b %d %Y\n%H:%M")


class UserDay(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'), index=True)
    date: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True))
    closing_balance: so.Mapped[float] = so.mapped_column(sa.Float)

    # Earning-related fields
    user_earning_id: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey('user_earning.id'),
        nullable=True,
        index=True
    )
    percentage_applied: so.Mapped[Optional[float]] = so.mapped_column(sa.Float, nullable=True)
    daily_earning: so.Mapped[Optional[float]] = so.mapped_column(sa.Float, nullable=True)

    # Relationships
    user: so.Mapped[User] = so.relationship(back_populates='days')
    user_earning: so.Mapped[Optional['UserEarning']] = so.relationship(
        back_populates='days',
        foreign_keys=[user_earning_id]
    )

    __table_args__ = (
        # Ensure one record per user per day
        sa.UniqueConstraint('user_id', 'date', name='_user_date_uc'),
        # Index for date range queries
        sa.Index('ix_user_day_user_date', 'user_id', 'date')
    )

    @property
    def date_est(self):
        return self.date.astimezone(nytz).strftime("%b %d %Y\n%H:%M")


class EarningStatus:
    PENDING = "Pending"
    APPROVED = "Approved"


class Earning(db.Model):
    """
    Represents an earning period with fixed and variable percentages.
    Requires double admin approval to be considered approved.
    """
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    start_date: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True))
    end_date: so.Mapped[datetime] = so.mapped_column(sa.DateTime(timezone=True))
    fixed_percentage: so.Mapped[float] = so.mapped_column(sa.Float)
    variable_percentage: so.Mapped[float] = so.mapped_column(sa.Float)
    status: so.Mapped[str] = so.mapped_column(
        sa.String(20),
        default=EarningStatus.PENDING
    )
    created_at: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(nytz)
    )
    created_by_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'))

    # Relationships
    created_by: so.Mapped[User] = so.relationship(
        back_populates='created_earnings',
    )
    user_earnings: so.Mapped[List['UserEarning']] = so.relationship(
        back_populates='earning',
        cascade='all, delete-orphan'
    )
    approvals: so.Mapped[List['EarningApproval']] = so.relationship(
        back_populates='earning',
        cascade='all, delete-orphan'
    )

    @property
    def days_in_period(self) -> int:
        """Calculate the number of days in the period"""
        return (self.end_date - self.start_date).days + 1

    @property
    def daily_fixed_percentage(self) -> float:
        """Calculate daily fixed percentage"""
        return self.fixed_percentage / self.days_in_period

    @property
    def daily_variable_percentage(self) -> float:
        """Calculate daily variable percentage"""
        return self.variable_percentage / self.days_in_period

    @property
    def start_date_est(self):
        return self.start_date.strftime("%b %d %Y")

    @property
    def end_date_est(self):
        return self.end_date.strftime("%b %d %Y")

    @property
    def created_at_est(self):
        return self.created_at.astimezone(nytz).strftime("%b %d %Y\n%H:%M")

    def add_approval(self, admin: User, approved: bool = True, notes: Optional[str] = None) -> 'EarningApproval':
        """Add admin approval with optional notes"""
        if not admin.is_admin:
            raise ValueError("Only admins can approve earnings")

        if self.status == EarningStatus.APPROVED:
            raise ValueError("Cannot approve already approved earnings")

        existing_approval = next(
            (a for a in self.approvals if a.admin_id == admin.id),
            None
        )
        if existing_approval:
            raise ValueError("Admin has already processed this earning")

        approval = EarningApproval(
            earning=self,
            admin=admin,
            approved=approved,
            notes=notes
        )
        db.session.add(approval)

        approval_count = sum(1 for a in self.approvals if a.approved)
        rejection_count = sum(1 for a in self.approvals if not a.approved)

        if rejection_count > 0:
            # Handle rejection logic if needed
            pass
        elif approval_count >= 2:
            self._approve_earning()

        db.session.commit()
        return approval

    def _approve_earning(self) -> None:
        """Approve the earning and update all user earnings to SETTLEMENT_PENDING"""
        self.status = EarningStatus.APPROVED

        # Update all user earnings to SETTLEMENT_PENDING
        for user_earning in self.user_earnings:
            user_earning.status = UserEarningStatus.SETTLEMENT_PENDING

        db.session.commit()

    def create_user_earnings(self) -> None:
        """
        Create UserEarning objects for all users.
        This method should be called right after creating the Earning period.
        """
        if self.status == EarningStatus.APPROVED:
            raise ValueError("Cannot create user earnings for approved periods")

        # Get all users
        users = User.query.where(User.is_admin.is_(False)).all()

        for user in users:
            # Skip if UserEarning already exists for this user and period
            existing = UserEarning.query.filter_by(
                user_id=user.id,
                earning_id=self.id
            ).first()

            if existing:
                continue

            # Create new UserEarning
            user_earning = UserEarning(
                user=user,
                earning=self,
                status=UserEarningStatus.DRAFT
            )
            db.session.add(user_earning)

        db.session.commit()

        # Now calculate earnings for each UserEarning
        for user_earning in self.user_earnings:
            user_earning.calculate_earnings()


class UserEarningStatus:
    DRAFT = "Draft"
    SETTLEMENT_PENDING = "Settlement pending"
    COMPLETE = "Complete"


class UserEarning(db.Model):
    """
    Represents earnings for a specific user for a specific period.
    Each UserEarning owns multiple UserDay objects for the period.
    """
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'), index=True)
    earning_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('earning.id'), index=True)
    earning_type: so.Mapped[Optional[str]] = so.mapped_column(sa.String(20))
    percentage: so.Mapped[Optional[float]] = so.mapped_column(sa.Float, default=0.0)
    total_amount: so.Mapped[float] = so.mapped_column(sa.Float, default=0.0)
    status: so.Mapped[str] = so.mapped_column(
        sa.String(20),
        default=UserEarningStatus.DRAFT
    )
    created_at: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(nytz)
    )
    completed_at: so.Mapped[Optional[datetime]] = so.mapped_column(sa.DateTime(timezone=True), nullable=True)

    # Relationships
    user: so.Mapped[User] = so.relationship(back_populates='user_earnings')
    earning: so.Mapped[Earning] = so.relationship(back_populates='user_earnings')
    days: so.Mapped[List['UserDay']] = so.relationship(
        back_populates='user_earning',
        cascade='all, delete-orphan',
        foreign_keys='UserDay.user_earning_id'
    )
    transactions: so.Mapped[List['Transaction']] = so.relationship(
        secondary=transaction_userearning,
        back_populates='user_earnings'
    )

    @property
    def created_at_est(self):
        return self.created_at.astimezone(nytz).strftime("%b %d %Y\n%H:%M")

    @property
    def completed_at_est(self):
        return self.completed_at.astimezone(nytz).strftime("%b %d %Y\n%H:%M")

    def calculate_earnings(self) -> float:
        """
        Calculate earnings for this user for the period.
        Assigns UserDay objects to this UserEarning and calculates daily earnings.

        Returns:
            Total earnings amount
        """
        # First, ensure user has days synced
        self.user.sync_user_days()

        # Find all UserDay objects for this user within the period
        user_days = UserDay.query.filter(
            UserDay.user_id == self.user_id,
            UserDay.date >= self.earning.start_date,
            UserDay.date <= self.earning.end_date,
            # Ensure no duplicate assignments
            UserDay.user_earning_id.is_(None)
        ).all()

        if not user_days:
            self.total_amount = 0.0
            db.session.commit()
            return 0.0

        self.earning_type = self.user.earning_type

        self.percentage = (
            self.earning.fixed_percentage if self.earning_type == EarningType.FIXED
            else self.earning.variable_percentage
        )

        # Determine appropriate percentage based on user type
        daily_percentage = (
            self.earning.daily_fixed_percentage if self.user.earning_type == EarningType.FIXED
            else self.earning.daily_variable_percentage
        )

        # Update user days with earning information
        total_earning = 0.0
        for day in user_days:
            # Assign to this UserEarning
            day.user_earning_id = self.id

            # Calculate daily earning
            day.percentage_applied = daily_percentage
            day.daily_earning = (day.closing_balance * daily_percentage) / 100
            total_earning += day.daily_earning

        self.total_amount = round(total_earning, 2)
        db.session.commit()

        return total_earning

    def link_transaction(self, transaction: Transaction) -> None:
        """
        Link a transaction to this user earning.

        Args:
            transaction: The transaction to link to this earning
        """
        if transaction not in self.transactions:
            self.transactions.append(transaction)
            db.session.commit()


class EarningApproval(db.Model):
    """
    Represents an admin approval of an earning period.
    """
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    earning_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('earning.id'), index=True)
    admin_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey('user.id'), index=True)
    approved: so.Mapped[bool] = so.mapped_column(sa.Boolean, default=True)
    notes: so.Mapped[Optional[str]] = so.mapped_column(sa.Text, nullable=True)
    created_at: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(nytz)
    )

    # Relationships
    earning: so.Mapped[Earning] = so.relationship(back_populates='approvals')
    admin: so.Mapped[User] = so.relationship(back_populates='earning_approvals')

    @property
    def created_at_est(self):
        return self.created_at.astimezone(nytz).strftime("%b %d %Y\n%H:%M")


class EarningService:
    @staticmethod
    def _get_month_boundaries(year: int, month: int) -> Tuple[datetime, datetime]:
        """
        Get the start and end datetime for a given month.

        Args:
            year: The year
            month: The month (1-12)

        Returns:
            Tuple of (start_date, end_date) as timezone-aware datetime
        """
        # Get first day of month
        first_day = datetime(year, month, 1, 0, 0, 0, tzinfo=nytz)

        # Get last day of month by finding days in month
        _, last_day_num = calendar.monthrange(year, month)
        last_day = datetime(year, month, last_day_num, 23, 59, 59, 999999, tzinfo=nytz)

        return first_day, last_day

    @staticmethod
    def _get_next_month(reference_date: Optional[datetime] = None) -> Tuple[int, int]:
        """
        Get the year and month following the provided reference date.
        If no reference date is provided, use the previous month from current date.

        Args:
            reference_date: Optional reference date

        Returns:
            Tuple of (year, month) for the next month
        """
        # If no reference date provided, use current date
        if reference_date is None:
            # Use current date as initial reference, replace day=1, subtract 1 day
            reference_date = datetime.now(nytz).replace(day=1) - timedelta(days=1)
            return reference_date.year, reference_date.month

        # Calculate next month
        year = reference_date.year
        month = reference_date.month

        # Move to next month
        if month == 12:
            return year + 1, 1
        else:
            return year, month + 1

    @staticmethod
    def create_earning_period(
            admin: User,
            year: Optional[int] = None,
            month: Optional[int] = None,
            fixed_percentage: float = 0.0,
            variable_percentage: float = 0.0
    ) -> Earning:
        """
        Create a new earning period for a specific month.
        If year and month are not provided, automatically selects the next
        chronological month after the latest existing earning period.

        Args:
            admin: The admin user creating the earning period
            year: Optional year (if not provided, will be auto-determined)
            month: Optional month (if not provided, will be auto-determined)
            fixed_percentage: The fixed percentage for the period
            variable_percentage: The variable percentage for the period

        Returns:
            The newly created Earning object
        """
        if not admin.is_admin:
            raise ValueError("Only admins can create earning periods")

        if fixed_percentage < 0 or variable_percentage < 0:
            raise ValueError("Percentages cannot be negative")

        # If year or month not provided, find the next chronological month
        if year is None or month is None:
            # Get the latest earning period
            latest_earning = Earning.query.order_by(Earning.end_date.desc()).first()

            if latest_earning:
                # Use the month after the latest earning period's end date
                reference_date = latest_earning.end_date
                year, month = EarningService._get_next_month(reference_date)
            else:
                # No existing earning, use the previous completed month
                year, month = EarningService._get_next_month()

        # Validate month and year
        if not (1 <= month <= 12):
            raise ValueError(f"Invalid month: {month}. Month must be between 1 and 12.")

        if year < 2000 or year > 2100:  # Reasonable year range
            raise ValueError(f"Invalid year: {year}. Year must be between 2000 and 2100.")

        # Get the start and end dates for this month
        start_date, end_date = EarningService._get_month_boundaries(year, month)

        today =datetime.now(nytz)

        if today <= end_date:
            raise ValueError(f"Next Earnings can be issued after {end_date.strftime("%B %d %Y")}")

        # Check for overlapping periods
        overlapping = Earning.query.filter(
            Earning.start_date <= end_date,
            Earning.end_date >= start_date
        ).first()

        if overlapping:
            raise ValueError(
                f"Overlapping period exists from {overlapping.start_date.date()} to {overlapping.end_date.date()}")

        # Create the earning period
        earning = Earning(
            start_date=start_date,
            end_date=end_date,
            fixed_percentage=fixed_percentage,
            variable_percentage=variable_percentage,
            created_by=admin
        )

        db.session.add(earning)
        db.session.commit()

        # Create UserEarning objects for all users
        earning.create_user_earnings()

        return earning

    @staticmethod
    def update_percentages(
            admin: User,
            earning: Earning,
            fixed_percentage: Optional[float] = None,
            variable_percentage: Optional[float] = None
    ) -> Earning:
        """Update percentages for a PENDING earning period and recalculate earnings"""
        if not admin.is_admin:
            raise ValueError("Only admins can update earning periods")

        if earning.status != EarningStatus.PENDING:
            raise ValueError("Cannot modify approved earning periods")

        changed = False

        if fixed_percentage is not None:
            if fixed_percentage < 0:
                raise ValueError("Fixed percentage cannot be negative")
            earning.fixed_percentage = fixed_percentage
            changed = True

        if variable_percentage is not None:
            if variable_percentage < 0:
                raise ValueError("Variable percentage cannot be negative")
            earning.variable_percentage = variable_percentage
            changed = True

        if changed:
            db.session.commit()

            # Recalculate user earnings
            for user_earning in earning.user_earnings:
                # First detach all UserDay objects
                for day in user_earning.days:
                    day.user_earning_id = None
                    day.percentage_applied = None
                    day.daily_earning = None

                db.session.commit()

                # Then recalculate
                user_earning.calculate_earnings()

        return earning
