from flask import Blueprint, render_template


pages = Blueprint('pages', __name__)


@pages.route('/')
def home():
    return render_template('home.html', page_key='home')


@pages.route('/topology')
def topology_page():
    return render_template('topology.html', page_key='topology')


@pages.route('/topology/fattree6')
def fattree6_page():
    return render_template('fattree6.html', page_key='fattree6')


@pages.route('/topology/your_topology')
def demo_page():
    return render_template('demo.html', page_key='your_topology')


@pages.route('/settings')
def settings_page():
    return render_template('settings.html', page_key='settings')