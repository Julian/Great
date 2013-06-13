import os


THIS_DIR = os.path.abspath(os.path.dirname(__file__))

DEBUG = True
SECRET_KEY = "903305a7-c6f8-4159-8073-0aa9eeba9163"

SQLALCHEMY_DATABASE_URI = "sqlite:////" + os.path.join(THIS_DIR, "great.db")
