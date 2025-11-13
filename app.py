import os
import cv2
import requests
import numpy as np
from deepface import DeepFace
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
from datetime import datetime
import secrets
import ast
from scipy.spatial import distance

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

POCKETBASE_URL = "http://127.0.0.1:8090"
ADMIN_TOKEN = "ton_token_admin_valide_ici"

# ➤ Fonction pour extraire les encodages faciaux avec DeepFace
def extract_face_encoding(image_path):
    print(f"Tentative de chargement de l'image : {image_path}")
    try:
        result = DeepFace.represent(img_path=image_path, model_name="Facenet", enforce_detection=True)
        print(f"Encodage généré : {len(result[0]['embedding'])} valeurs")
        encoding = result[0]['embedding']
        if encoding:
            return encoding
        else:
            print("Aucun visage détecté")
            return None
    except Exception as e:
        print(f"Erreur de traitement de l'image : {e}")
        return None

# ➤ Fonction pour extraire l'encodage d'un frame en mémoire
def extract_face_encoding_from_frame(frame):
    try:
        temp_path = os.path.join("static", "temp_frame.jpg")
        cv2.imwrite(temp_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        encoding = extract_face_encoding(temp_path)
        os.remove(temp_path)
        return encoding
    except Exception as e:
        print(f"Erreur de traitement du frame : {e}")
        return None

# ➤ Enregistrer un étudiant
def save_user_to_pocketbase(name, role, encoding, image_path=None):
    data = {
        "name": name,
        "role": role,
        "face_embedding": encoding
    }
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            files = {"image": (os.path.basename(image_path), image_file, "image/jpeg")}
            response = requests.post(
                f"{POCKETBASE_URL}/api/collections/etudiants/records",
                data=data,
                files=files,
                headers=headers
            )
            return response.json()
    else:
        response = requests.post(
            f"{POCKETBASE_URL}/api/collections/etudiants/records",
            json=data,
            headers=headers
        )
        return response.json()

def get_students_from_pocketbase():
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    response = requests.get(f"{POCKETBASE_URL}/api/collections/etudiants/records", headers=headers)
    return response.json().get("items", [])

def record_attendance(student_id, status):
    date = datetime.now().strftime("%Y-%m-%d")
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    check = requests.get(
        f"{POCKETBASE_URL}/api/collections/presences/records?filter=etudiantId='{student_id}' && date='{date}'",
        headers=headers
    )
    if check.json().get("items"):
        return True
    data = {"etudiantId": student_id, "date": date, "present": status}
    response = requests.post(f"{POCKETBASE_URL}/api/collections/presences/records", json=data, headers=headers)
    return response.status_code == 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_name = request.form['user_id']
        students = get_students_from_pocketbase()
        for student in students:
            if student['name'] == user_name:
                session['user_id'] = student['name']
                session['role'] = student['role']
                return redirect(url_for('scan'))
        return render_template('login.html', error="Utilisateur non trouvé")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        role = request.form['role']
        image_file = request.files['image']

        image_path = os.path.join("static", "temp.jpg")
        image_file.save(image_path)

        encoding = extract_face_encoding(image_path)
        if encoding is None:
            os.remove(image_path)
            return render_template('register.html', error="Aucun visage détecté")

        user_data = save_user_to_pocketbase(name, role, encoding, image_path)
        os.remove(image_path)

        if "error" in user_data:
            return render_template('register.html', error=user_data["error"])
        return render_template('register.html', message=f"Inscription réussie pour {name} !")
    return render_template('register.html')

@app.route('/scan', methods=['GET', 'POST'])
def scan():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'uploaded_image' in request.files:
            image_file = request.files['uploaded_image']
            image_path = os.path.join("static", "temp_scan.jpg")
            image_file.save(image_path)

            scanned_encoding = extract_face_encoding(image_path)
            os.remove(image_path)

            if scanned_encoding is None:
                return jsonify({"error": "Aucun visage détecté dans l'image scannée"})

            students = get_students_from_pocketbase()
            matched_student = None
            best_distance = float('inf')

            for student in students:
                stored_encoding = student.get('face_embedding')
                if stored_encoding:
                    if isinstance(stored_encoding, str):
                        try:
                            stored_encoding = ast.literal_eval(stored_encoding)
                        except Exception as e:
                            print(f"Erreur conversion JSON : {e}")
                            continue

                    try:
                        distance_value = distance.euclidean(np.array(stored_encoding), np.array(scanned_encoding))
                        print(f"Distance avec {student['name']} : {distance_value}")

                        if distance_value < best_distance:
                            best_distance = distance_value
                            matched_student = student
                    except Exception as e:
                        print(f"Erreur comparaison : {e}")

            if matched_student and best_distance < 10.0:
                if record_attendance(matched_student['id'], True):
                    return jsonify({
                        "message": f"Présent - {matched_student['name']} reconnu avec une distance de {round(best_distance, 4)}"
                    })
                else:
                    return jsonify({"error": "Erreur lors de l'enregistrement"})
            else:
                return jsonify({
                    "message": f"Aucun visage correspondant trouvé (distance minimale = {round(best_distance, 4)})"
                })
        elif 'camera_scan' in request.form:
            return redirect(url_for('camera_scan'))

    subjects = [{"id": "1", "name": "Mathématiques"}]
    return render_template('scan.html', subjects=subjects)

@app.route('/camera_scan')
def camera_scan():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('camera_scan.html')

@app.route('/video_feed')
def video_feed():
    """Route pour diffuser le flux vidéo de la caméra (images uniquement)."""
    def generate_frames():
        cap = cv2.VideoCapture(0)  # Ouvre la caméra par défaut (0)
        if not cap.isOpened():
            print("Erreur : Impossible d'ouvrir la caméra.")
            yield b'--frame\r\nContent-Type: text/plain\r\n\r\nCamera not accessible\r\n'
            return

        while True:
            success, frame = cap.read()
            if not success:
                print("Erreur : Impossible de capturer le frame.")
                break
            else:
                ret, buffer = cv2.imencode('.jpg', frame)
                if not ret:
                    print("Erreur : Impossible d'encoder le frame.")
                    continue
                frame = buffer.tobytes()
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'

        cap.release()

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/recognition_feed')
def recognition_feed():
    """Route pour diffuser les résultats de la reconnaissance faciale."""
    def generate_recognition():
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            yield f"data: Erreur : Impossible d'ouvrir la caméra.\n\n"
            return

        frame_count = 0
        while True:
            success, frame = cap.read()
            if not success:
                yield f"data: Erreur : Impossible de capturer le frame.\n\n"
                break

            # Traiter un frame toutes les 5 frames pour éviter une surcharge
            frame_count += 1
            if frame_count % 5 != 0:
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            encoding = extract_face_encoding_from_frame(frame_rgb)
            if encoding:
                students = get_students_from_pocketbase()
                matched_student = None
                best_distance = float('inf')

                for student in students:
                    stored_encoding = student.get('face_embedding')
                    if stored_encoding:
                        if isinstance(stored_encoding, str):
                            try:
                                stored_encoding = ast.literal_eval(stored_encoding)
                            except Exception as e:
                                print(f"Erreur conversion JSON : {e}")
                                continue

                        try:
                            distance_value = distance.euclidean(np.array(stored_encoding), np.array(encoding))
                            print(f"Distance avec {student['name']} : {distance_value}")

                            if distance_value < best_distance:
                                best_distance = distance_value
                                matched_student = student
                        except Exception as e:
                            print(f"Erreur comparaison : {e}")

                if matched_student and best_distance < 10.0:
                    if record_attendance(matched_student['id'], True):
                        yield f"data: Présent - {matched_student['name']} reconnu avec une distance de {round(best_distance, 4)}\n\n"
                    else:
                        yield f"data: Erreur lors de l'enregistrement de la présence.\n\n"
                    break
                else:
                    yield f"data: Aucun visage correspondant trouvé (distance minimale = {round(best_distance, 4)})\n\n"
            else:
                yield f"data: Aucun visage détecté dans le frame.\n\n"

        cap.release()

    return Response(generate_recognition(), mimetype='text/event-stream')

@app.route('/attendance')
def attendance():
    if 'user_id' not in session or session['role'] != 'teacher':
        return redirect(url_for('login'))

    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    response = requests.get(f"{POCKETBASE_URL}/api/collections/presences/records", headers=headers)
    attendances = response.json().get("items", [])
    return render_template('attendance.html', attendances=attendances)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)