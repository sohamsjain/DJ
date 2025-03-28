from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, FloatField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, NumberRange, Optional, ValidationError


class TransactionForm(FlaskForm):
    amount = FloatField('Amount', validators=[
        DataRequired(message="Amount can't be empty"),
        NumberRange(min=0.01, message="Amount must be greater than 0")
    ])
    reference_id = StringField('Reference ID', validators=[Optional()])
    description = TextAreaField('Description', validators=[Optional()])
    proof_of_transaction = FileField('Proof of Transaction', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Images and PDFs only!')
    ])
    submit = SubmitField('Submit')


class SettlementForm(FlaskForm):
    amount = FloatField('Amount')
    reference_id = StringField('Reference ID', validators=[Optional()])
    description = TextAreaField('Description', validators=[Optional()])
    proof_of_transaction = FileField('Proof of Transaction', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Images and PDFs only!')
    ])
    submit = SubmitField('Submit')


class UpdateProofForm(FlaskForm):
    proof_of_transaction = FileField('Proof of Transaction', validators=[
        FileRequired(),
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Images and PDFs only!')
    ])
    submit = SubmitField('Update Proof')


class ApprovalForm(FlaskForm):
    notes = TextAreaField('Notes', validators=[Optional()])
    approve = SubmitField('Approve')
    reject = SubmitField('Reject')


class UpdateEarningForm(FlaskForm):
    """Form for updating an earning period's percentages."""
    fixed_percentage = FloatField('Fixed Percentage (%)',
                                  validators=[DataRequired(), NumberRange(min=0, max=100)])
    variable_percentage = FloatField('Variable Percentage (%)',
                                     validators=[DataRequired(), NumberRange(min=0, max=100)])
    submit = SubmitField('Update & Recalculate')