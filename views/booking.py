from flask import Blueprint, render_template

booking_bp = Blueprint("booking", __name__)


@booking_bp.route("/agendamento")
def agendamento():
    return render_template("agendamento.html")
