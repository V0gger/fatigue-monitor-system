import os
import cv2
import dlib
import numpy as np
from scipy.spatial import distance as dist
from imutils import face_utils
import time
import winsound
import threading
import psycopg2
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# ================= ШРИФТ =================
try:
    FONT = ImageFont.truetype("arial.ttf", 20)
    FONT_SMALL = ImageFont.truetype("arial.ttf", 16)
    FONT_LARGE = ImageFont.truetype("arial.ttf", 24)
except:
    FONT = ImageFont.load_default()
    FONT_SMALL = FONT
    FONT_LARGE = FONT

def put_text_rus(img, text, position, color=(255, 255, 255), font=FONT_SMALL):
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    color_rgb = (color[2], color[1], color[0])
    draw.text(position, text, font=font, fill=color_rgb)
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

# ================= DB =================
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "fatigue_monitor"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD"), # Пароль берется из .env, дефолта нет для безопасности
    port=os.getenv("DB_PORT", "5432")
)
cursor = conn.cursor()

def get_or_create_user(login="Admin"):
    cursor.execute("SELECT id_user FROM users WHERE login=%s", (login,))
    user = cursor.fetchone()
    if user:
        return user[0]
    cursor.execute(
        """INSERT INTO users (login, password_hash, role) 
           VALUES (%s, %s, %s) RETURNING id_user""",
        (login, 'hashed_password_123', 'operator')
    )
    conn.commit()
    return cursor.fetchone()[0]

def start_session(user_id):
    cursor.execute("""
        INSERT INTO sessions (id_user, start_time)
        VALUES (%s, NOW())
        RETURNING id_session
    """, (user_id,))
    conn.commit()
    return cursor.fetchone()[0]

def log_event(session_id, event_type, duration=0, ear=0, perclos=0, severity=0):
    cursor.execute("""
        INSERT INTO events (
            id_session, event_time, event_type, duration, ear_value, perclos_value, severity
        )
        VALUES (%s, NOW(), %s, %s, %s, %s, %s)
    """, (session_id, event_type, float(duration), float(ear), float(perclos), severity))
    conn.commit()

def save_profile(user_id, max_ear, ear_thresh):
    cursor.execute("""
        UPDATE users 
        SET max_ear = %s, ear_threshold = %s, profile_updated_at = NOW()
        WHERE id_user = %s
    """, (float(max_ear), float(ear_thresh), user_id))
    conn.commit()

def close_session(session_id):
    cursor.execute("""
        UPDATE sessions
        SET end_time = NOW(), status = 'finished'
        WHERE id_session = %s
    """, (session_id,))
    conn.commit()

# ================= EAR =================
def eye_aspect_ratio(eye):
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])
    C = dist.euclidean(eye[0], eye[3])
    return (A + B) / (2.0 * C)

# ================= UI =================
def draw_status_bar(frame, status, ear, thresh, perclos, blinks, session_time):
    status_colors = {
        "Бодр": (0, 255, 0),
        "Усталость (Долгое моргание)": (0, 255, 255),
        "Усталость (PERCLOS)": (0, 165, 255),
        "Микросон": (0, 0, 255)
    }
    
    recommendations = {
        "Бодр": "Продолжайте работу",
        "Усталость (Долгое моргание)": "Сделайте перерыв 5 минут",
        "Усталость (PERCLOS)": "Рекомендуется отдых",
        "Микросон": "ВНИМАНИЕ! Прекратите работу!"
    }
    
    cv2.rectangle(frame, (0, 0), (640, 140), (20, 20, 20), -1)
    
    color = status_colors.get(status, (0, 0, 255))
    frame = put_text_rus(frame, f"[{status}]", (10, 5), color, FONT_LARGE)
    
    rec = recommendations.get(status, "")
    frame = put_text_rus(frame, rec, (10, 35), (255, 255, 255), FONT_SMALL)
    
    hours = int(session_time // 3600)
    minutes = int((session_time % 3600) // 60)
    frame = put_text_rus(frame, f"Сессия: {hours}ч {minutes}м", (10, 60), (200, 200, 200), FONT_SMALL)
    
    frame = put_text_rus(frame, f"EAR: {ear:.2f}", (350, 5), (0, 255, 255), FONT_SMALL)
    frame = put_text_rus(frame, f"Порог: {thresh:.2f}", (350, 30), (0, 255, 0), FONT_SMALL)
    
    perclos_percent = int(perclos * 100)
    bar_width = int(perclos_percent * 1.5)
    cv2.rectangle(frame, (350, 60), (350 + bar_width, 75), (0, 255, 0), -1)
    cv2.rectangle(frame, (350, 60), (500, 75), (255, 255, 255), 1)
    frame = put_text_rus(frame, f"PERCLOS: {perclos_percent}%", (350, 82), (255, 255, 0), FONT_SMALL)
    
    frame = put_text_rus(frame, f"Морганий: {blinks}", (350, 110), (255, 255, 255), FONT_SMALL)
    
    return frame

# ================= SOUND =================
alarm_active = False
last_beep_time = 0

def play_microsleep_alarm():
    global alarm_active
    alarm_active = True
    while alarm_active:
        winsound.Beep(2500, 700)

def stop_alarm():
    global alarm_active
    alarm_active = False

def play_warning_beep():
    global last_beep_time
    if time.time() - last_beep_time < 2:
        return
    last_beep_time = time.time()
    for _ in range(3):
        winsound.Beep(2000, 150)
        time.sleep(0.1)

# ================= НАСТРОЙКИ =================
MIN_BLINK_DURATION = 0.08
MAX_BLINK_DURATION = 0.5
BLINK_COOLDOWN = 0.15
HYSTERESIS = 0.02
MIN_EAR_DROP = 0.02
MAX_DELTA_TIME = 0.08
EAR_SMOOTHING = 0.6

# ================= СОСТОЯНИЯ =================
eye_closed = False
eye_closed_time = 0.0
last_blink_time = 0
TOTAL_BLINKS = 0
alert_thread = None
last_microsleep_log = 0

# ================= УСТАЛОСТЬ =================
CLOSED_EYES_TIME_LIMIT = 3
LONG_BLINK_THRESHOLD = 0.5
fatigue_status = "Бодр"

# ================= PERCLOS =================
PERCLOS_TIME_WINDOW = 60
THRESHOLD_PERCLOS = 0.12
perclos_start_time = time.time()
closed_time_total = 0

# ================= КАЛИБРОВКА =================
calibration_start_time = time.time()
calibration_duration = 10
calibrated = False
max_EAR = 0
EYE_AR_THRESH = None

# ================= ВРЕМЯ СЕССИИ =================
fatigue_start_time = time.time()

# ================= CV =================
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")

(lStart, lEnd) = face_utils.FACIAL_LANDMARKS_IDXS["left_eye"]
(rStart, rEnd) = face_utils.FACIAL_LANDMARKS_IDXS["right_eye"]

video_capture = cv2.VideoCapture(0)
video_capture.set(cv2.CAP_PROP_FPS, 30)

prev_time = time.time()
prev_ear = None

# ================= INIT DB =================
USER_ID = get_or_create_user()
SESSION_ID = start_session(USER_ID)

# ================= MAIN LOOP =================
try:
    while True:
        ret, frame = video_capture.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detector(gray, 0)

        current_time = time.time()
        delta_time = min(current_time - prev_time, MAX_DELTA_TIME)
        prev_time = current_time

        for face in faces:
            shape = predictor(gray, face)
            shape = face_utils.shape_to_np(shape)

            leftEye = shape[lStart:lEnd]
            rightEye = shape[rStart:rEnd]

            raw_ear = (eye_aspect_ratio(leftEye) + eye_aspect_ratio(rightEye)) / 2.0
            ear = raw_ear if prev_ear is None else EAR_SMOOTHING * prev_ear + (1 - EAR_SMOOTHING) * raw_ear
            prev_ear = ear

            if not calibrated:
                max_EAR = max(max_EAR, ear)
                if time.time() - calibration_start_time >= calibration_duration:
                    EYE_AR_THRESH = max_EAR * 0.8
                    calibrated = True
                    save_profile(USER_ID, max_EAR, EYE_AR_THRESH)
                frame = put_text_rus(frame, "Калибровка...", (10, 60), (0, 255, 255), FONT)
                continue

            closed_condition = ear < (EYE_AR_THRESH - MIN_EAR_DROP)
            open_condition = ear > (EYE_AR_THRESH + HYSTERESIS)

            if closed_condition:
                eye_closed_time += delta_time
                closed_time_total += delta_time
                if not eye_closed:
                    eye_closed = True
                if eye_closed_time > CLOSED_EYES_TIME_LIMIT:
                    fatigue_status = "Микросон"
                    if current_time - last_microsleep_log > 5:
                        log_event(SESSION_ID, "microsleep", eye_closed_time, severity=2)
                        last_microsleep_log = current_time
                    if alert_thread is None or not alert_thread.is_alive():
                        alert_thread = threading.Thread(target=play_microsleep_alarm, daemon=True)
                        alert_thread.start()

            elif open_condition:
                if eye_closed:
                    blink_duration = eye_closed_time
                    if (MIN_BLINK_DURATION < blink_duration < MAX_BLINK_DURATION and
                            current_time - last_blink_time > BLINK_COOLDOWN):
                        TOTAL_BLINKS += 1
                        last_blink_time = current_time
                        log_event(SESSION_ID, "blink", blink_duration, ear)
                        if blink_duration > LONG_BLINK_THRESHOLD:
                            fatigue_status = "Усталость (Долгое моргание)"
                            log_event(SESSION_ID, "long_blink", blink_duration, severity=1)
                            threading.Thread(target=play_warning_beep, daemon=True).start()
                if alarm_active:
                    stop_alarm()
                eye_closed = False
                eye_closed_time = 0

            if current_time - perclos_start_time >= PERCLOS_TIME_WINDOW:
                perclos = closed_time_total / PERCLOS_TIME_WINDOW
                if perclos > THRESHOLD_PERCLOS:
                    fatigue_status = "Усталость (PERCLOS)"
                    log_event(SESSION_ID, "perclos_alert", perclos=perclos, severity=1)
                    threading.Thread(target=play_warning_beep, daemon=True).start()
                closed_time_total = 0
                perclos_start_time = current_time

            perclos_now = closed_time_total / PERCLOS_TIME_WINDOW

            session_time = time.time() - fatigue_start_time
            frame = draw_status_bar(frame, fatigue_status, ear, EYE_AR_THRESH, 
                                    perclos_now, TOTAL_BLINKS, session_time)

        cv2.imshow("Fatigue Monitor", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    video_capture.release()
    close_session(SESSION_ID)
    conn.close()
    cv2.destroyAllWindows()