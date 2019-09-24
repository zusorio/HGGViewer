import ast
import re
import requests
import requests_cache
from functools import wraps
from datetime import datetime, timedelta, date
from flask import Flask, redirect, request, render_template, url_for, make_response

app = Flask(__name__)
requests_cache.install_cache(backend="memory", expire_after=3)
session = requests.Session()


def need_cookies(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.cookies.get("cookies") != "yes":
            return redirect(url_for("route"))
        return f(*args, **kwargs)
    return decorated_function


def start_of_week(week):
    return datetime.strptime(f"1 {week-1} {datetime.now().year}", "%w %W %Y")


def get_class_list():
    try:
        response = session.get(
            "http://www.hgg-markgroeningen.de/pages/hgg/verwaltung/vertretungsplan/Schueler/frames/navbar.htm")
    except requests.exceptions.ConnectionError:
        return None
    if response.status_code != 200:
        return None
    all_classes = ast.literal_eval(re.search("var classes = (.*);", response.text).group(1))
    pattern = re.compile("([0-9][0-9]?[A-F]|[0-9]{4})")
    available_classes = [s for s in all_classes if pattern.match(s)]
    available_other = [s for s in all_classes if not pattern.match(s)]
    return available_classes, available_other


def get_class_info(class_name):
    class_list = get_class_list()
    if class_name not in class_list[0]:
        return None
    if class_list:
        zeros_required = 5 - len(str(class_list[0].index(class_name)))
        c_key = "c" + zeros_required * "0" + str(class_list[0].index(class_name) + 1)
        current_week_number = datetime.now().isocalendar()[1]
        response = session.get(
            f"http://www.hgg-markgroeningen.de/pages/hgg/verwaltung/vertretungsplan/Schueler/{current_week_number}/c/{c_key}.htm")
        info = re.search('([0-9][0-9]?[A-F]|[0-9]{4})(&nbsp;</font><fontface="Arial">)([A-Z]{3}|[0-9]{4})',
                         response.text.replace(" ", "").replace("\n", ""))
        class_name = info.group(1)
        teacher_name = info.group(3)
        return {
            "teacher": teacher_name,
            "class": class_name,
            "c_key": c_key
        }


def get_plans(class_name):
    class_info = get_class_info(class_name)
    if not class_info:
        return None
    current_week = datetime.now()
    test_weeks = [(current_week + timedelta(weeks=x)).isocalendar()[1] for x in range(5)]

    available_plans = []
    for week in test_weeks:
        response = session.get(
            f"http://www.hgg-markgroeningen.de/pages/hgg/verwaltung/vertretungsplan/Schueler/{week}/c/{class_info['c_key']}.htm")
        if response.status_code == 200:
            fixed_html = response.text.replace("../../untisinfo.css",
                                               url_for("static", filename="untisinfo.css")).replace(
                "\n", "")

            pattern = '<font size="6" face="Arial" color="#0000FF">(.*)&nbsp;</font>'
            target = start_of_week(week).strftime("%d.%m.%y")
            fixed_html = re.sub(pattern, f'<font size="6" face="Arial" color="#0000FF">{target}&nbsp;</font>',
                                fixed_html)

            pattern2 = '<font face="Arial">(.*)</font><BR><TABLE border="3" rules="all" cellpadding="1" cellspacing="1">'

            target2 = ""

            days_until_start = (start_of_week(week) - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).days

            if days_until_start < -1:
                target2 = f"Hat vor {abs(days_until_start)} Tagen angefangen"
            elif days_until_start == -1:
                target2 = "Hat vor einem Tag angefangen"
            elif days_until_start == 0:
                target2 = "Fängt heute an"
            elif days_until_start == 1:
                target2 = "Fängt morgen an"
            elif days_until_start > 1:
                target2 = f"Fängt in {days_until_start} Tagen an"

            fixed_html = re.sub(pattern2,
                                f'<font face="Arial">{target2}</font><BR><TABLE border="3" rules="all" cellpadding="1" cellspacing="1">',
                                fixed_html)
            available_plans.append({
                "url": f"http://www.hgg-markgroeningen.de/pages/hgg/verwaltung/vertretungsplan/Schueler/{week}/c/{class_info['c_key']}.htm",
                "html": fixed_html,
                "week": week
            })
    return available_plans


@app.route("/")
def route():
    cookies = request.cookies.get("cookies")
    if cookies:
        if cookies == "yes":
            if request.cookies.get("class"):
                return redirect(url_for("plan"))
            else:
                return redirect(url_for("select"))
        else:
            return redirect(url_for("no_cookies"))
    else:
        return render_template("landing.html")


@app.route("/select/")
@need_cookies
def select():
    class_list = get_class_list()
    if class_list:
        return render_template("select.html", available_classes=class_list[0])
    else:
        return "Irgendwas ist falsch gelaufen... Tut uns leid"


@app.route("/select/submit/", methods=["POST"])
@need_cookies
def accept_selection():
    selected_class = request.values.get("selected_class", None)
    if selected_class:
        resp = make_response(redirect(url_for("route")))
        resp.set_cookie("class", selected_class, expires=(datetime.now() + timedelta(days=365)))
        return resp
    else:
        return redirect(url_for("route"))


@app.route("/plan/")
@need_cookies
def plan():
    class_name = request.cookies.get("class")
    if class_name:
        available_plans = get_plans(class_name)
        if not available_plans:
            return "Hmm... Irgendwas ist falsch gelaufen"
        info = get_class_info(class_name)
        return render_template("view.html", available_plans=available_plans, info=info)
    else:
        return redirect(url_for("select"))


@app.route("/plan/nocookies/")
def no_cookies():
    class_list = get_class_list()
    if class_list:
        return render_template("select_no_cookies.html", available_classes=class_list[0])
    else:
        return "Irgendwas ist falsch gelaufen... Tut uns leid"


@app.route("/plan/nocookies/view/")
def no_cookies_view():
    class_name = request.args.get("selected_class")
    available_plans = get_plans(class_name)
    if not available_plans:
        return "Hmm... Irgendwas ist falsch gelaufen"
    info = get_class_info(class_name)
    return render_template("view.html", available_plans=available_plans, info=info)


@app.route("/cookies/")
def cookies():
    return render_template("cookies.html")


@app.route("/cookies/accept/")
def cookies_accept():
    resp = make_response(redirect(url_for("route")))
    resp.set_cookie("cookies", "yes", expires=(datetime.now() + timedelta(days=365)))
    return resp


@app.route("/cookies/decline/")
def cookies_decline():
    resp = make_response(redirect(url_for("route")))
    resp.set_cookie("cookies", "no", expires=(datetime.now() + timedelta(days=365)))
    return resp

@app.route("/privacy/")
def privacy():
    return render_template("privacy.html")

if __name__ == '__main__':
    app.run()
