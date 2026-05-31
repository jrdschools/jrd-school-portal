from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "JRD_SUPER_SECRET_KEY_2026")

# 🔑 गूगल शीट कनेक्ट करने का नया 100% सुरक्षित लॉजिक (बिना फाइल वाला)
def connect_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # रेंडर के सीक्रेट बॉक्स (Environment) से सीधे चाबी उठाना
    creds_json = os.environ.get("GOOGLE_CREDS_JSON")
    
    if creds_json:
        # अगर रेंडर सर्वर पर लाइव हैं तो डायरेक्ट टेक्स्ट से क्रेडेंशियल बनाएगा
        info = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
    else:
        # अगर लोकल कंप्यूटर पर टेस्टिंग कर रहे हैं तो फाइल से उठाएगा
        creds_path = os.path.join(os.path.dirname(__file__), 'secret.json')
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        
    client = gspread.authorize(creds)
    return client.open("JRD Attendance")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'name' not in session:
        return redirect(url_for('index'))
    return render_template('dashboard.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    try:
        sheet_file = connect_google_sheet()
        info_sheet = sheet_file.worksheet('Staff_Info')
        all_records = info_sheet.get_all_records()
        
        for row in all_records:
            db_login = str(row.get('Login', '')).strip()
            db_pass = str(row.get('Password', '')).strip()
            
            if db_login == username and db_pass == password:
                session['name'] = row.get('Teacher_Name')
                session['role'] = str(row.get('Role', 'TEACHER')).upper().strip()
                session['assigned_class'] = row.get('Assigned_Class', '')
                
                return jsonify({"status": "success", "role": session['role']})
                
        return jsonify({"status": "error", "message": "गलत यूज़र आईडी या密码!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"डेटाबेस एरर: {str(e)}"})

@app.route('/get_session_info', methods=['GET'])
def get_session_info():
    if 'name' in session:
        return jsonify({
            "status": "success",
            "name": session['name'],
            "role": session['role'],
            "assigned_class": session['assigned_class']
        })
    return jsonify({"status": "error"})

@app.route('/get_students', methods=['GET'])
def get_students():
    class_name = request.args.get('class', '').strip()
    try:
        sheet_file = connect_google_sheet()
        att_sheet = sheet_file.worksheet('attendance')
        all_rows = att_sheet.get_all_records()
        
        students_list = []
        for row in all_rows:
            s_class = str(row.get('Class', '')).strip()
            if s_class.lower() == class_name.lower():
                students_list.append({
                    "student_name": row.get('Student Name'),
                    "father_name": row.get("Father's Name"),
                    "mobile": row.get('Mobile'),
                    "status": row.get('Status', 'ABSENT')
                })
        return jsonify({"status": "success", "students": students_list})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/save_student_attendance', methods=['POST'])
def save_student_attendance():
    data = request.json
    records = data.get('records', [])
    
    try:
        sheet_file = connect_google_sheet()
        att_sheet = sheet_file.worksheet('attendance')
        
        cell_matrix = att_sheet.get_all_values()
        headers = cell_matrix[0]
        
        name_idx = headers.index('Student Name')
        status_idx = headers.index('Status')
        time_idx = headers.index('Time')
        msg_idx = headers.index('Msg_Sent')
        
        now = datetime.now()
        formatted_time = now.strftime("%I:%M %p %d-%m-%Y")
        
        update_cells_list = []
        
        for record in records:
            s_name = record.get('student_name')
            new_status = record.get('status')
            
            for r_idx, row in enumerate(cell_matrix[1:], start=2):
                if row[name_idx] == s_name:
                    cell_status = att_sheet.cell(r_idx, status_idx + 1)
                    cell_status.value = new_status
                    update_cells_list.append(cell_status)
                    
                    cell_time = att_sheet.cell(r_idx, time_idx + 1)
                    cell_time.value = formatted_time
                    update_cells_list.append(cell_time)
                    
                    cell_msg = att_sheet.cell(r_idx, msg_idx + 1)
                    if new_status == "ABSENT":
                        cell_msg.value = "SEND_NOW_PENDING"
                    else:
                        cell_msg.value = "PRESENT_OVERRIDE"
                    update_cells_list.append(cell_msg)
                    break
        
        if update_cells_list:
            att_sheet.update_cells(update_cells_list)
                    
        return jsonify({"status": "success", "message": "डेटा लाइव गूगल शीट में ओवरराइड होकर सुरक्षित सेव हो गया है!"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"सेव करने में एरर: {str(e)}"})

@app.route('/admin/get_teachers', methods=['GET'])
def admin_get_teachers():
    try:
        sheet_file = connect_google_sheet()
        info_sheet = sheet_file.worksheet('Staff_Info')
        all_records = info_sheet.get_all_records()
        
        teachers = []
        for row in all_records:
            if str(row.get('Role')).upper().strip() != 'ADMIN':
                teachers.append({
                    "name": row.get('Teacher_Name'),
                    "class": row.get('Assigned_Class')
                })
        return jsonify({"status": "success", "teachers": teachers})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/admin/get_leaves', methods=['GET'])
def admin_get_leaves():
    try:
        return jsonify({"status": "success", "leaves": []})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.after_request
def add_header(response):
    response.headers['X-Frame-Options'] = 'ALLOWALL'
    return response

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
