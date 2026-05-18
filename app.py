import email
from os import name
import re

from flask import Flask,render_template, request, redirect,session,url_for
from models import db,Hospital,Booking,User
from sqlalchemy import func
from werkzeug.security import  generate_password_hash , check_password_hash
from flask import send_file

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter

import io

app = Flask(__name__)
app.secret_key = "medtrack_secret"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hospital.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# HOME PAGE
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/main")
def main():
    return render_template("index.html")

# DASHBOARD
@app.route("/dashboard")
def dashboard():

    total_hospitals = Hospital.query.count()
    total_bookings = Booking.query.count()

    icu_total = db.session.query(func.sum(Hospital.icu_beds)).scalar()
    oxygen_total = db.session.query(func.sum(Hospital.oxygen_beds)).scalar()
    normal_total = db.session.query(func.sum(Hospital.normal_beds)).scalar()

    return render_template(
        "dashboard.html",
        total_hospitals=total_hospitals,
        total_bookings=total_bookings,
        icu_total=icu_total,
        oxygen_total=oxygen_total,
        normal_total=normal_total
    )

# ADD HOSPITAL
@app.route("/add_hospital", methods=["GET", "POST"])
def add_hospital():

    if session.get("role") != "admin":
        return "Access Denied"

    if request.method == "POST":

        name = request.form["hospital_name"]
        city = request.form["city"]
        address = request.form["address"]
        icu = int(request.form["icu_beds"])
        oxygen = int(request.form["oxygen_beds"])
        normal = int(request.form["normal_beds"])

        new_hospital = Hospital(
            hospital_name=name,
            city=city,
            address=address,
            icu_beds=icu,
            oxygen_beds=oxygen,
            normal_beds=normal
        )

        db.session.add(new_hospital)
        db.session.commit()

        return redirect("/")

    return render_template("add_hospital.html")

# VIEW HOSPITALS
@app.route("/hospitals")
def view_hospitals():

    if "user" not in session:
        return redirect("/login")

    search = request.args.get("search")
    booking_id = request.args.get("booking_id") 

    if search:
        hospitals = Hospital.query.filter(
            (Hospital.hospital_name.contains(search)) |
            (Hospital.city.contains(search))
        ).all()
    else:
        hospitals = Hospital.query.order_by(Hospital.id).all()
    staff_members = User.query.filter_by(role="staff", approval_status="approved").all()
    
    return render_template("view_hospitals.html", hospitals=hospitals, staff_members=staff_members)

# BOOK BED
@app.route("/book/<int:hospital_id>", methods=["GET", "POST"])
def book_bed(hospital_id):

    if "user" not in session:
        return redirect("/login")

    hospital = Hospital.query.get(hospital_id)

    # Get booking_id (for modify case)
    booking_id = request.args.get("booking_id")

    if request.method == "POST":

        name = request.form["patient_name"]

        # Guardian details
        guardian_name = request.form["guardian_name"]

        relationship = request.form["relationship"]

        guardian_email = request.form["email"]

        guardian_phone = request.form["guardian_phone"]

        bed_type = request.form["bed_type"]

        priority = request.form["priority"]

        # =========================================================
        # STEP 1: Handle OLD booking (when modifying)
        # =========================================================

        if booking_id and booking_id != "None":

            old_booking = Booking.query.get(int(booking_id))

            if old_booking:

                old_hospital = Hospital.query.get(
                    old_booking.hospital_id
                )

                if old_booking.bed_type == "ICU":

                    old_hospital.icu_beds += 1

                elif old_booking.bed_type == "Oxygen":

                    old_hospital.oxygen_beds += 1

                elif old_booking.bed_type == "Normal":

                    old_hospital.normal_beds += 1

                db.session.delete(old_booking)

        # =========================================================
        # STEP 2: CHECK BED AVAILABILITY
        # =========================================================

        if bed_type == "ICU":

            if hospital.icu_beds > 0:

                hospital.icu_beds -= 1

            else:

                return "ICU bed not available"

        elif bed_type == "Oxygen":

            if hospital.oxygen_beds > 0:

                hospital.oxygen_beds -= 1

            else:

                return "Oxygen bed not available"

        elif bed_type == "Normal":

            if hospital.normal_beds > 0:

                hospital.normal_beds -= 1

            else:

                return "Normal bed not available"

        # =========================================================
        # STEP 3: CREATE NEW BOOKING
        # =========================================================

        new_booking = Booking(

            patient_name=name,

            email=guardian_email,

            phone=guardian_phone,

            guardian_name=guardian_name,

            relationship=relationship,

            guardian_phone=guardian_phone,

            hospital_id=hospital.id,

            bed_type=bed_type,

            priority=priority,

            status="Confirmed"
        )

        db.session.add(new_booking)

        db.session.commit()

        return redirect(f"/payment/{new_booking.id}")

    return render_template(
        "book.html",
        hospital=hospital
    )
# VIEW BOOKINGS
@app.route("/view_bookings")
def view_bookings():

    if session.get("role") not in ["admin", "staff"]:
        return redirect(url_for("login"))

    bookings = Booking.query.order_by(Booking.priority).all()

    return render_template("view_bookings.html", bookings=bookings)

# CANCEL BOOKING
@app.route("/cancel/<int:booking_id>")
def cancel_booking(booking_id):

    booking = Booking.query.get_or_404(booking_id)

    # if already cancelled do nothing
    if booking.status == "Cancelled":
        return redirect("/my_bookings")

    hospital = Hospital.query.get(booking.hospital_id)

    if booking.bed_type == "ICU":
        hospital.icu_beds += 1

    elif booking.bed_type == "Oxygen":
        hospital.oxygen_beds += 1

    elif booking.bed_type == "Normal":
        hospital.normal_beds += 1

    booking.status = "Cancelled"
    
    if booking.payment_method:
        booking.refund_status = "Pending"
    db.session.commit()

    return redirect("/my_bookings")

# DISCHARGE BOOKING
@app.route("/discharge/<int:booking_id>")
def discharge_booking(booking_id):

    booking = Booking.query.get_or_404(booking_id)

    # prevent wrong discharge
    if booking.status != "Confirmed":
        return redirect("/view_bookings")

    hospital = Hospital.query.get(booking.hospital_id)

    # increase bed count back
    if booking.bed_type == "ICU":
        hospital.icu_beds += 1
    elif booking.bed_type == "Oxygen":
        hospital.oxygen_beds += 1
    elif booking.bed_type == "Normal":
        hospital.normal_beds += 1

    # update status
    booking.status = "Discharged"

    db.session.commit()

    return redirect("/view_bookings")

@app.route("/modify/<int:booking_id>", methods=["GET","POST"])
def modify_booking(booking_id):

    booking = Booking.query.get(booking_id)
    hospital = Hospital.query.get(booking.hospital_id)

    if request.method == "POST":

        new_bed = request.form["bed_type"]

        # Increase old bed
        if booking.bed_type == "ICU":
            hospital.icu_beds += 1
        elif booking.bed_type == "Oxygen":
            hospital.oxygen_beds += 1
        elif booking.bed_type == "Normal":
            hospital.normal_beds += 1

        # Decrease new bed
        if new_bed == "ICU":
            hospital.icu_beds -= 1
        elif new_bed == "Oxygen":
            hospital.oxygen_beds -= 1
        elif new_bed == "Normal":
            hospital.normal_beds -= 1

        booking.bed_type = new_bed

        db.session.commit()

        return redirect("/bookings")

    return render_template("modify_booking.html", booking=booking)

@app.route("/register", methods=["GET", "POST"])
def register():

    role = request.args.get("role")

    if request.method == "POST":
        role = request.form.get("role")

        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]

        # Check existing user
        if User.query.filter_by(email=email).first():
            return render_template("register.html", error="User already exists!", role=role)

        # Password validation (hidden rules)
        if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$',password):

            error = "Invalid password format!!"

            return render_template(
                "register.html",
                 error=error,
                 role=role
    )
        # Hash password
        hashed_password = generate_password_hash(password)

        approval_status = "approved" 
        if role == "staff":
            approval_status = "pending"

        new_user = User(
            name=name,
            email=email,
            phone=phone,
            password=hashed_password,
            role=role,
            approval_status=approval_status
        )

        db.session.add(new_user)
        db.session.commit()

        return redirect(f"/login?role={role}")

    return render_template("register.html", role=role)
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    role = request.args.get("role") or request.form.get("role")

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            if user.role == "staff" and user.approval_status != "approved":
                error = "Waiting for admin approval"
                return render_template("login.html", error=error, role=role)

            # 🔒 IMPORTANT: Role match check
            if user.role != role:
                error = "Access denied for this role"
                return render_template("login.html", error=error, role=role)

            session["user"] = user.email
            session["role"] = user.role

            if user.role == "admin":
                return redirect("/admin_dashboard")
            elif user.role == "staff":
                return redirect("/staff_dashboard")
            else:
                return redirect("/patient_dashboard")

        else:
            error = "Invalid Email or Password"

    return render_template("login.html", error=error, role=role)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/payment/<int:booking_id>", methods=["GET", "POST"])
def payment(booking_id):

    booking = Booking.query.get_or_404(booking_id)

    # Calculate fee
    if booking.bed_type == "ICU":
        fee = 1000

    elif booking.bed_type == "Oxygen":
        fee = 700

    else:
        fee = 500

    error = None

    if request.method == "POST":

        method = request.form.get("payment_method")

        # UPI VALIDATION
        if method == "UPI":

            upi_id = request.form.get("upi_id")

            if not upi_id or "@" not in upi_id:
                error = "Enter valid UPI ID"

                return render_template(
                    "payment.html",
                    booking=booking,
                    fee=fee,
                    error=error
                )

        # SAVE PAYMENT DETAILS
        booking.payment_method = method

        booking.payment_amount = fee

        booking.transaction_id = "TXN" + str(booking.id) + "2026"

        booking.status = "Confirmed"

        db.session.commit()

        return render_template(
            "payment_success.html",
            booking=booking
        )

    return render_template(
        "payment.html",
        booking=booking,
        fee=fee,
        error=error
    )

@app.route("/forgot_password")
def forgot_password():
    return render_template("forgot_password.html")

@app.route("/admin_dashboard")
def admin_dashboard():

    total = Booking.query.count()

    pending = Booking.query.filter_by(status="Pending").count()

    confirmed = Booking.query.filter_by(status="Confirmed").count()

    cancelled = Booking.query.filter_by(status="Cancelled").count()

    discharged = Booking.query.filter_by(status="Discharged").count()

    pending_staff = User.query.filter_by(role="staff", approval_status="pending").all()
    hospitals = Hospital.query.all()
    return render_template(
        "admin_dashboard.html",
        total=total,
        pending=pending,
        confirmed=confirmed,
        cancelled=cancelled,
        discharged=discharged,
        pending_staff=pending_staff,
        hospitals=hospitals
    )

@app.route("/staff_dashboard")
def staff_dashboard():

    if "user" not in session:
        return redirect("/")

    # Get logged in staff
    user = User.query.filter_by(
        email=session["user"]
    ).first()

    # Get assigned hospital
    hospital = Hospital.query.get(
        user.assigned_hospital_id
    )

    return render_template(
        "staff_dashboard.html",
        user=user,
        hospital=hospital
    )

@app.route("/patient_dashboard")
def patient_dashboard():

    if session.get("role") != "patient":
        return "Access Denied"

    return render_template("patient_dashboard.html")

@app.route("/pending_staff")
def pending_staff():

    # ✅ only admin can access
    if session.get("role") != "admin":
        return redirect("/")

    # get pending staff
    staff_requests = User.query.filter_by(
        role="staff",
        approval_status="pending"
    ).all()

    hospitals = Hospital.query.all()

    return render_template(
        "pending_staff.html",
        staff_requests=staff_requests,
        hospitals=hospitals
    )

@app.route("/approve_staff/<int:user_id>", methods=["POST"])
def approve_staff(user_id):

    if session.get("role") != "admin":
        return redirect("/")

    staff = User.query.get_or_404(user_id)

    hospital_id = request.form.get("hospital_id")

    hospital = Hospital.query.get(hospital_id)

    # approve
    staff.approval_status = "approved"

    # assign selected hospital
    staff.assigned_hospital_id = hospital_id

    # notification
    if hospital:
        staff.notification = (
            f"You are approved and assigned to "
            f"{hospital.hospital_name}"
        )

    db.session.commit()

    return redirect("/admin_dashboard")

@app.route("/reject_staff/<int:user_id>")
def reject_staff(user_id):

    # only admin
    if session.get("role") != "admin":
        return redirect("/")

    # get user
    staff = User.query.get_or_404(user_id)

    # delete user
    db.session.delete(staff)

    # save changes
    db.session.commit()

    return redirect("/admin_dashboard")

@app.route("/assigned_staff")
def assigned_staff():

    # only admin
    if session.get("role") != "admin":
        return redirect("/")

    # approved staff only
    staff_list = User.query.filter_by(
        role="staff",
        approval_status="approved"
    ).all()

    hospitals = Hospital.query.all()

    return render_template(
        "assigned_staff.html",
        staff_list=staff_list,
        hospitals=hospitals
    )

@app.route("/download_receipt/<int:booking_id>")
def download_receipt(booking_id):

    booking = Booking.query.get_or_404(booking_id)

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter
    )

    styles = getSampleStyleSheet()

    content = []

    content.append(
        Paragraph(
            "MedTrack Hospital Bed Booking Receipt",
            styles['Title']
        )
    )

    content.append(Spacer(1, 20))

    content.append(
        Paragraph(
            f"<b>Patient Name:</b> {booking.patient_name}",
            styles['BodyText']
        )
    )

    content.append(
        Paragraph(
            f"<b>Hospital Name:</b> {booking.hospital.hospital_name}",
            styles['BodyText']
        )
    )

    content.append(
        Paragraph(
            f"<b>Guardian Name:</b> {booking.guardian_name}",
            styles['BodyText']
        )
    )

    content.append(
        Paragraph(
            f"<b>Guardian Phone:</b> {booking.guardian_phone}",
            styles['BodyText']
        )
    )

    content.append(
        Paragraph(
            f"<b>Hospital Name:</b> {booking.hospital.hospital_name}",
            styles['BodyText']
        )
    )

    content.append(
        Paragraph(
            f"<b>Bed Type:</b> {booking.bed_type}",
            styles['BodyText']
        )
    )

    content.append(
        Paragraph(
            f"<b>Status:</b> {booking.status}",
            styles['BodyText']
        )
    )

    doc.build(content)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="receipt.pdf",
        mimetype="application/pdf"
    )



@app.route("/my_bookings")
def my_bookings():

    if session.get("role") != "patient":
        return "Access Denied"

    bookings = Booking.query.filter_by(email=session.get("user")).all()

    return render_template("my_bookings.html", bookings=bookings)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # Hospital.query.delete()
        # db.session.commit()

        import csv

        # with app.app_context():
        if Hospital.query.count() == 0:

            with open('karnataka_hospitals.csv', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)

                for row in reader:
                # existing_hospital = Hospital.query.filter_by(
                #     hospital_name=row['hospital_name'],
                #     city=row['city']
                # ).first()
                # if existing_hospital:
                #     continue
                    hospital = Hospital(
                        hospital_name=row['hospital_name'],
                        city=row['city'],
                        address=row['address'],
                        icu_beds=int(row['icu_beds']),
                        oxygen_beds=int(row['oxygen_beds']),
                        normal_beds=int(row['normal_beds'])
                    )

                    db.session.add(hospital)

                db.session.commit()

        print("Hospitals imported successfully!")

        admin = User.query.filter_by(email="admin@gmail.com").first()

        if not admin:
            admin = User(
                name="Admin",
                email="admin@gmail.com",
                phone="9999999999",
                password=generate_password_hash("admin123"),
                role="admin"
            )
            db.session.add(admin)
            db.session.commit()
    app.run(debug=True)