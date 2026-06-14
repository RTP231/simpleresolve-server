import requests


def create_session():
    session = requests.Session()
    session.headers.update({'X-App-Version': '2.0'})
    return session
