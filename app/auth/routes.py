from urllib.parse import urlsplit
from flask import render_template, url_for, flash, redirect, request
from flask_login import login_user, logout_user, current_user
from app.auth import bp
from app.auth.forms import SignupForm, LoginForm
from app.models import User, db


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = SignupForm()
    if form.validate_on_submit():
        try:
            user = User(username=form.name.data, email=form.email.data.lower())
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Account created successfully!', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            flash('An error occurred while creating your account.', 'error')
            print(f"Error: {str(e)}")

    return render_template('auth/signup.html', form=form)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        print(form.email.data)
        user: User = User.query.filter_by(email=form.email.data.lower()).first()

        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password', 'error')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('main.dashboard')
        return redirect(next_page)
    return render_template('auth/login.html', title='Sign In', form=form)


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))