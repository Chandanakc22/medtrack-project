from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100))

    email = db.Column(db.String(100), unique=True)

    phone = db.Column(db.String(15))

    password = db.Column(db.String(200))

    role = db.Column(db.String(20))

    # NEW FIELDS
    approval_status = db.Column(
        db.String(20),
        default="approved"
    )

    assigned_hospital_id = db.Column(
        db.Integer,
        db.ForeignKey('hospital.id'),
        nullable=True
    )

    # ADD THIS
    hospital = db.relationship("Hospital",foreign_keys=[assigned_hospital_id])

    notification = db.Column(
        db.String(200),
        nullable=True
    )

class Hospital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_name = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(300))

    icu_beds = db.Column(db.Integer, default=0)
    oxygen_beds = db.Column(db.Integer, default=0)
    normal_beds = db.Column(db.Integer, default=0)

    staff_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    patient_name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))

    guardian_name = db.Column(db.String(100))
    guardian_phone = db.Column(db.String(20))
    relationship = db.Column(db.String(50))

    bed_type = db.Column(db.String(50))
    priority = db.Column(db.String(50))
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'))
    hospital = db.relationship("Hospital",backref="bookings")

    status = db.Column(db.String(50), default="Pending")

    payment_method = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    payment_amount = db.Column(db.Float)


    refund_status = db.Column(db.String(50), default="Not Applicable")

    hospital =db.relationship("Hospital")

