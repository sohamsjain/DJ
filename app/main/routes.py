import os
from werkzeug.utils import secure_filename
from flask import render_template, url_for, request, flash, redirect, current_app, send_from_directory, abort
from flask_login import login_required, current_user
from app.main import bp
from app.main.forms import TransactionForm, UpdateProofForm, ApprovalForm, UpdateEarningForm, SettlementForm
from app.models import *


@bp.route("/")
@bp.route("/index")
def index():
    return redirect(url_for('auth.login'))


@login_required
@bp.route("/dashboard")
def dashboard():
    if current_user.is_admin:
        return redirect(url_for('main.users'))
    return redirect(url_for('main.user', id=current_user.id))


@login_required
@bp.route("/users")
def users():
    if not current_user.is_admin:
        abort(403)
    _users = User.query.where(User.is_admin == False).all()
    total_balance = sum([u.balance for u in _users])
    return render_template("users.html", title='Users', users=_users, total_balance=total_balance)


@login_required
@bp.route("/user/<int:id>")
def user(id):
    _user: User = User.query.get_or_404(id)

    if not (current_user.is_admin or current_user == _user):
        abort(403)

    # Get statistics
    statistics = _user.get_statistics()

    # Get pending transactions
    pending_transactions = _user.get_transactions(status=TransactionStatus.APPROVAL_PENDING)

    # Get unpaid earnings
    unpaid_earnings = _user.get_user_earnings(status=UserEarningStatus.SETTLEMENT_PENDING)

    # Get all earnings
    user_earnings = (UserEarning.query.filter_by(user_id=id).where(UserEarning.status != UserEarningStatus.DRAFT)
                     .order_by(UserEarning.created_at.desc())).all()

    # Get all transactions
    _transactions = _user.get_transactions()

    return render_template(
        "user.html",
        title=f'User: {_user.username}',
        user=_user,
        statistics=statistics,
        pending_transactions=pending_transactions,
        unpaid_earnings=unpaid_earnings,
        user_earnings=user_earnings,
        transactions=_transactions,
        active_tab=request.args.get('tab', 'summary')
    )


@login_required
@bp.route("/transactions")
def transactions():
    if not current_user.is_admin:
        abort(403)
    _transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
    return render_template("transactions.html", transactions=_transactions, title="Transactions")


@login_required
@bp.route("/user/<int:id>/deposit", methods=['GET', 'POST'])
def deposit(id):
    _user: User = User.query.get_or_404(id)

    if not (current_user.is_admin or
            current_user == _user):
        abort(403)

    form = TransactionForm()
    if form.validate_on_submit():
        # Handle file upload
        proof_file = None
        if form.proof_of_transaction.data:
            filename = secure_filename(form.proof_of_transaction.data.filename)
            # Create a unique filename with user_id and timestamp
            base, ext = os.path.splitext(filename)
            unique_filename = f"{base}_{id}_{int(datetime.now().timestamp())}{ext}"

            # Ensure the upload directory exists
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'transaction_proofs')
            os.makedirs(upload_dir, exist_ok=True)

            # Save the file
            file_path = os.path.join(upload_dir, unique_filename)
            form.proof_of_transaction.data.save(file_path)
            proof_file = f"transaction_proofs/{unique_filename}"

        try:
            # Create the transaction
            transaction = _user.initiate_transaction(
                amount=form.amount.data,
                type=TransactionType.DEPOSIT,
                proof_of_transaction=proof_file,
                reference_id=form.reference_id.data,
                description=form.description.data
            )
            flash('Deposit request submitted successfully!', 'success')
            return redirect(url_for('main.transaction', id=transaction.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template(
        "transaction_form.html",
        title=f'Deposit Form - {_user.username}',
        user=_user,
        form=form,
        transaction_type='Deposit'
    )


@login_required
@bp.route("/user/<int:id>/withdraw", methods=['GET', 'POST'])
def withdraw(id):
    _user = User.query.get_or_404(id)

    if not (current_user.is_admin or
            current_user == _user):
        abort(403)

    form = TransactionForm()
    if form.validate_on_submit():
        # Handle file upload
        proof_file = None
        if form.proof_of_transaction.data:
            filename = secure_filename(form.proof_of_transaction.data.filename)
            # Create a unique filename with user_id and timestamp
            base, ext = os.path.splitext(filename)
            unique_filename = f"{base}_{id}_{int(datetime.now().timestamp())}{ext}"

            # Ensure the upload directory exists
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'transaction_proofs')
            os.makedirs(upload_dir, exist_ok=True)

            # Save the file
            file_path = os.path.join(upload_dir, unique_filename)
            form.proof_of_transaction.data.save(file_path)
            proof_file = f"transaction_proofs/{unique_filename}"

        try:
            # Create the transaction
            transaction = _user.initiate_transaction(
                amount=form.amount.data,
                type=TransactionType.WITHDRAWAL,
                proof_of_transaction=proof_file,
                reference_id=form.reference_id.data,
                description=form.description.data
            )
            flash('Withdrawal request submitted successfully!', 'success')
            return redirect(url_for('main.transaction', id=transaction.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template(
        "transaction_form.html",
        title=f'Withdrawal Form - {_user.username}',
        user=_user,
        form=form,
        transaction_type='Withdrawal'
    )


@login_required
@bp.route("/user/<int:id>/settle", methods=['GET', 'POST'])
def settle(id):
    _user = User.query.get_or_404(id)

    if not current_user.is_admin:
        abort(403)

    unpaid_earnings = _user.get_statistics()['earnings_unpaid']

    form = SettlementForm()
    if form.validate_on_submit():
        # Handle file upload
        proof_file = None
        if form.proof_of_transaction.data:
            filename = secure_filename(form.proof_of_transaction.data.filename)
            # Create a unique filename with user_id and timestamp
            base, ext = os.path.splitext(filename)
            unique_filename = f"{base}_{id}_{int(datetime.now().timestamp())}{ext}"

            # Ensure the upload directory exists
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'transaction_proofs')
            os.makedirs(upload_dir, exist_ok=True)

            # Save the file
            file_path = os.path.join(upload_dir, unique_filename)
            form.proof_of_transaction.data.save(file_path)
            proof_file = f"transaction_proofs/{unique_filename}"

        try:
            # Create the transaction
            transaction = _user.initiate_transaction(
                amount=unpaid_earnings,
                type=TransactionType.EARNINGS,
                proof_of_transaction=proof_file,
                reference_id=form.reference_id.data,
                description=form.description.data
            )
            flash('Settlement request submitted successfully!', 'success')
            return redirect(url_for('main.transaction', id=transaction.id))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template(
        "transaction_form.html",
        title=f'Settle Earnings - {_user.username}',
        user=_user,
        unpaid_earnings=unpaid_earnings,
        form=form,
        transaction_type='Earnings'
    )


@login_required
@bp.route("/transaction/<int:id>", methods=['GET', 'POST'])
def transaction(id):
    _transaction = Transaction.query.get_or_404(id)

    if not (current_user.is_admin or
            current_user.id == _transaction.user_id):
        abort(403)

    update_proof_form = UpdateProofForm()
    approval_form = ApprovalForm()
    current_user_has_approved = current_user in [approval.admin for approval in _transaction.approvals]

    # Update proof of transaction
    if update_proof_form.validate_on_submit() and request.form.get('action') == 'update_proof':
        if _transaction.status != TransactionStatus.APPROVAL_PENDING:
            flash('Cannot update proof for non-pending transactions', 'danger')
        else:
            # Handle file upload
            filename = secure_filename(update_proof_form.proof_of_transaction.data.filename)
            # Create a unique filename with transaction_id and timestamp
            base, ext = os.path.splitext(filename)
            unique_filename = f"{base}_{id}_{int(datetime.now().timestamp())}{ext}"

            # Ensure the upload directory exists
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'transaction_proofs')
            os.makedirs(upload_dir, exist_ok=True)

            # Save the file
            file_path = os.path.join(upload_dir, unique_filename)
            update_proof_form.proof_of_transaction.data.save(file_path)

            # Update transaction with new proof
            new_proof = f"transaction_proofs/{unique_filename}"
            try:
                _transaction.update_proof(new_proof)
                flash('Proof of transaction updated successfully!', 'success')
            except ValueError as e:
                flash(str(e), 'danger')

        return redirect(url_for('main.transaction', id=id))

    # Handle approval/rejection
    if approval_form.validate_on_submit() and request.form.get('action') == 'approve':
        if not current_user.is_admin:
            flash('Only administrators can approve transactions', 'danger')
        else:
            try:
                approved = True if approval_form.approve.data else False
                _transaction.add_approval(
                    admin=current_user,
                    approved=approved,
                    notes=approval_form.notes.data
                )
                if approved:
                    flash('Transaction approved successfully!', 'success')
                else:
                    flash('Transaction rejected!', 'warning')
            except ValueError as e:
                flash(str(e), 'danger')

        return redirect(url_for('main.transaction', id=id))

    return render_template(
        "transaction.html",
        title=f'Transaction #{_transaction.id}',
        transaction=_transaction,
        update_proof_form=update_proof_form,
        approval_form=approval_form,
        current_user_has_approved=current_user_has_approved
    )


@login_required
@bp.route('/uploads/<path:filename>')
def download_file(filename):
    # Security check: only allow access to files in the UPLOAD_FOLDER directory
    if '..' in filename or filename.startswith('/'):
        abort(404)

    # Make sure the user is authorized to access this file
    # This is a simple check; you might want to implement more sophisticated authorization
    if not current_user.is_authenticated:
        abort(403)

    return send_from_directory(
        os.path.join(current_app.config['UPLOAD_FOLDER']),
        filename,
        as_attachment=True
    )


@bp.route("/earnings")
@login_required
def earnings():
    """List all earnings periods."""
    if not current_user.is_admin:
        abort(403)

    # Get all earnings periods, ordered by start date descending
    earnings = Earning.query.order_by(Earning.start_date.desc()).all()

    return render_template(
        "earnings.html",
        title='Earnings Periods',
        earnings=earnings
    )


@bp.route("/earnings/create")
@login_required
def create_earning():
    """Create a new earnings period."""
    if not current_user.is_admin:
        abort(403)

    try:
        # Create the earning period using the service
        earning = EarningService.create_earning_period(admin=current_user)

        flash(f'New Earning created successfully!',
              'success')
        return redirect(url_for('main.earnings'))

    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('main.earnings'))


@bp.route("/earning/<int:id>", methods=['GET', 'POST'])
@login_required
def earning(id):
    """View a specific earnings period."""
    if not current_user.is_admin:
        abort(403)

    earning = Earning.query.get_or_404(id)

    update_form = UpdateEarningForm()
    approval_form = ApprovalForm()

    # Populate form with current values for GET request
    if request.method == 'GET':
        update_form.fixed_percentage.data = earning.fixed_percentage
        update_form.variable_percentage.data = earning.variable_percentage

    # Get all user earnings for this period
    user_earnings = UserEarning.query.filter_by(earning_id=earning.id).all()

    # Calculate totals
    fixed_total = sum(ue.total_amount for ue in user_earnings if ue.earning_type == EarningType.FIXED)
    variable_total = sum(ue.total_amount for ue in user_earnings if ue.earning_type == EarningType.VARIABLE)
    grand_total = fixed_total + variable_total

    # Determine if current user has already approved
    current_user_has_approved = current_user in [approval.admin for approval in earning.approvals]

    return render_template(
        "earning.html",
        title=f'Earning Period Details',
        earning=earning,
        update_form=update_form,
        approval_form=approval_form,
        user_earnings=user_earnings,
        fixed_total=fixed_total,
        variable_total=variable_total,
        grand_total=grand_total,
        current_user_has_approved=current_user_has_approved
    )


@bp.route("/earning/<int:id>/update", methods=['POST'])
@login_required
def update_earning(id):
    """Update an earnings period's percentages."""
    if not current_user.is_admin:
        abort(403)

    earning = Earning.query.get_or_404(id)

    # Check if the earning is in a state that allows updates
    if earning.status != EarningStatus.PENDING:
        flash('Cannot update approved earning periods', 'danger')
        return redirect(url_for('main.earning', id=id))

    form = UpdateEarningForm()

    if form.validate_on_submit():
        try:
            EarningService.update_percentages(
                admin=current_user,
                earning=earning,
                fixed_percentage=form.fixed_percentage.data,
                variable_percentage=form.variable_percentage.data
            )
            flash('Percentages updated and earnings recalculated successfully!', 'success')
        except ValueError as e:
            flash(str(e), 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", 'danger')

    return redirect(url_for('main.earning', id=id))


@bp.route("/earning/<int:id>/approve", methods=['POST'])
@login_required
def approve_earning(id):
    """Approve an earnings period."""
    if not current_user.is_admin:
        abort(403)

    earning = Earning.query.get_or_404(id)
    form = ApprovalForm()

    if form.validate_on_submit():
        try:
            earning.add_approval(
                admin=current_user,
                approved=True,
                notes=form.notes.data
            )
            flash('Earning period approved successfully!', 'success')
        except ValueError as e:
            flash(str(e), 'danger')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", 'danger')

    return redirect(url_for('main.earning', id=id))


@bp.route("/userearning/<int:id>", methods=['GET'])
@login_required
def userearning(id):
    """View details of a specific user earning."""
    user_earning = UserEarning.query.get_or_404(id)

    # Check permissions
    if not (current_user.is_admin or current_user.id == user_earning.user_id):
        abort(403)

    # Get all days associated with this earning
    days = UserDay.query.filter_by(user_earning_id=user_earning.id).order_by(UserDay.date).all()

    return render_template(
        "user_earning.html",
        title=f'Earning Details for {user_earning.user.username}',
        user_earning=user_earning,
        days=days
    )
