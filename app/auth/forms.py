from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
import sqlalchemy as sa
from app.models import User
from app import db


class SignupForm(FlaskForm):
    name = StringField('Name', validators=[
        DataRequired("Name is required"),
        Length(min=2, max=50)
    ])

    email = StringField('Email address', validators=[
        DataRequired("Email is required"),
        Email()
    ])

    password = PasswordField('Password', validators=[
        DataRequired("Password is required"),
        Length(min=8, message="Password must be at least 8 characters long")
    ])

    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired("Password Confirmation is required"),
        EqualTo('password', message='Passwords must match')
    ])

    agree = BooleanField('I agree with the terms and conditions', validators=[
        DataRequired(message="You must agree to the terms and conditions")
    ])

    def validate_email(self, email):
        user = db.session.scalar(sa.select(User).where(
            User.email == email.data))
        if user is not None:
            raise ValidationError('Please use a different email address.')


class LoginForm(FlaskForm):
    email = StringField('Your email', validators=[
        DataRequired(),
        Email()
    ])

    password = PasswordField('Password', validators=[
        DataRequired()
    ])

    remember = BooleanField('Remember me')