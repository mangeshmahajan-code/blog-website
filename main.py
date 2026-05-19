from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash ,request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm,RegisterForm,LoginForm,CommentForm
import os
from dotenv import load_dotenv
import smtplib

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_KEY')
ckeditor = CKEditor(app)
Bootstrap5(app)
gravatar = Gravatar(
    app,
    size=100,
    rating='g',
    default='retro',
    force_default=False,
    force_lower=False,
    use_ssl=False,
    base_url=None
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User,user_id)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass
app.config['SQLALCHEMY_DATABASE_URI'] =os.getenv('DB_URL')
db = SQLAlchemy(model_class=Base)
db.init_app(app)

class User (UserMixin,db.Model):
    __tablename__ ='users'
    id : Mapped[int] = mapped_column(Integer,primary_key=True)
    name : Mapped[str] = mapped_column(String(20),nullable=False)
    email : Mapped[str] = mapped_column(String(80),nullable=False,unique=True) 
    password : Mapped[str] = mapped_column(String,nullable=False)
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship('Comment',back_populates='comment_author')

# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id :Mapped[int] = mapped_column(Integer,db.ForeignKey('users.id'))
    author = relationship('User',back_populates='posts')
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    comments = relationship('Comment',back_populates='parent_post')

class Comment (db.Model):
    __tablename__ ='comments'
    id : Mapped[int] = mapped_column(Integer,primary_key=True)

    author_id : Mapped[int] = mapped_column(Integer,db.ForeignKey('users.id'))    
    comment_author = relationship('User',back_populates='comments')

    post_id : Mapped[int] = mapped_column(Integer,db.ForeignKey('blog_posts.id'))
    parent_post = relationship('BlogPost',back_populates='comments')

    text : Mapped[str] = mapped_column(String,nullable=False)

with app.app_context():
    db.create_all()

def admin_only(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if current_user.id != 1:
            abort(403)

        return function(*args, **kwargs)

    return wrapper

@app.route('/register',methods=['GET','POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data
        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        
        if user :
            flash("You've already signed up with that email, log in instead!")
            return redirect('login')
        
        new_user = User(
            name = form.name.data,
            email = email,
            password = generate_password_hash(form.password.data,method='pbkdf2:sha256',salt_length=8)
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('get_all_posts'))
    return render_template("register.html",form = form)

 
@app.route('/login',methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        if user :
            if check_password_hash(user.password,password):
                login_user(user)
                return redirect(url_for('get_all_posts'))
            else :
                flash('invalid password.Please enter correct password')
        else:
            flash('invalid email please check email')
    return render_template("login.html",form = form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)



@app.route("/post/<int:post_id>",methods=['GET','POST'])
def show_post(post_id):
    form = CommentForm()    
    requested_post = db.get_or_404(BlogPost, post_id)
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.")
            return redirect(url_for("login"))
        new_comment = Comment(
            comment_author=current_user,
            parent_post=requested_post,   
            text = form.comment.data,
        )
        db.session.add(new_comment)
        db.session.commit()
        return redirect(url_for('show_post', post_id=post_id))
    all_comments = db.session.execute(db.select(Comment).order_by(Comment.id.desc())).scalars().all()
    return render_template("post.html", post=requested_post,form =form,comments = all_comments, gravatar=gravatar)

@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)

@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)

@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact",methods=['POST','GET'])
def contact():
    if request.method== 'POST':
        name = request.form.get("name")
        email= request.form.get("email")
        phone = request.form.get("phone")
        message = request.form.get("message")
        send_email(name,email,phone,message)

        return render_template("contact.html",msg_sent=True)
    return render_template("contact.html")

def send_email(name,email,phone,message):

    my_email = os.getenv('MY_EMAIL')
    password = os.getenv('PASSWORD')

    message = f"Subject: New Message\n\nName:{name}\nEmail:{email}\nPhone:{phone}\nMessage:{message}"

    connection = smtplib.SMTP("smtp.gmail.com",587)
    connection.starttls()

    connection.login(user=my_email,password=password)

    connection.sendmail(
        from_addr=my_email,
        to_addrs=my_email,
        msg=message
    )

    connection.close()

if __name__ == "__main__":
    app.run(debug=False)
