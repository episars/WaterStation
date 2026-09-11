import tkinter as tk
import os
os.environ['LG_WD'] = '/tmp'
from PIL import Image, ImageTk
from tkinter import ttk
from gpiozero import DigitalInputDevice, OutputDevice
#from gpiozero.pins.lgpio import LGPIOFactory
from gpiozero import Device
#Device.pin_factory = LGPIOFactory()
import time
import threading

# ---------------- GPIO Setup ----------------
flow_sensor = DigitalInputDevice(22, pull_up=True)
ro_valve = OutputDevice(17, active_high=False, initial_value=False)
coffee_valve = OutputDevice(27, active_high=False, initial_value=False)

Pulses_per_liter_RO = 2025
Pulses_per_liter_coffee = 2050
concentrate_ppm = 550
target_ppm = 85
calibration_mode = False
calibration_start_pulses = 0
coffeeWaterRatio = (concentrate_ppm - target_ppm) / target_ppm

pulse_count = 0
pulse_lock = threading.Lock()
pin = 0
duration = 0
concentrate_duration = 0
drinkWaterEnabled = False
coffeeWaterEnabled = False
sleepTime = 60
sleepBrightness = 10
fullBrightness = 125
sleepEnabled = False
currentTime = 0
def calc_pulses_needed():
    return [
        1.25 * Pulses_per_liter_coffee, .9 * Pulses_per_liter_RO, 1 * Pulses_per_liter_RO,
        .2 * Pulses_per_liter_RO, .2 * Pulses_per_liter_RO, .325 * Pulses_per_liter_RO
    ]

pulses_needed = calc_pulses_needed()

valve_start_time = None
MAX_VALVE_OPEN_TIME = 600

root = None
status_var = None
progress_var = None

# ---------------- Backlight ----------------
def set_brightness(level):
    try:
        with open("/sys/class/backlight/10-0045/brightness", "w") as file:
            file.write(str(level))
    except FileNotFoundError:
        pass
    except PermissionError:
        print("Permission denied. Try running with sudo.")

# ---------------- Callbacks ----------------
def pulse_callback():
    global pulse_count
    with pulse_lock:
        pulse_count += 1

flow_sensor.when_activated = pulse_callback

def xor(a, b):
    return (a and not b) or (not a and b)

# ---------------- Control Loop ----------------
def control_gpio():
    global pulse_count, drinkWaterEnabled, coffeeWaterEnabled
    global pin, sleepEnabled, duration, concentrate_duration, coffeeWaterRatio
    global currentTime, valve_start_time, calibration_mode

    try:
        while True:
            time.sleep(0.005)

            # Backlight control
            set_brightness(sleepBrightness if sleepEnabled else fullBrightness)

            if xor(drinkWaterEnabled, coffeeWaterEnabled):
                with pulse_lock:
                    current_pulses = pulse_count

                # Only start safety timer after first pulse is received
                if current_pulses > 0 and valve_start_time is None:
                    valve_start_time = time.time()

                # Safety cutoff
                if not calibration_mode and valve_start_time and (time.time() - valve_start_time) > MAX_VALVE_OPEN_TIME:
                    print("Safety cutoff: valve open too long.")
                    ro_valve.off()
                    coffee_valve.off()
                    drinkWaterEnabled = False
                    coffeeWaterEnabled = False
                    with pulse_lock:
                        pulse_count = 0
                    sleepEnabled = True
                    valve_start_time = None
                    if root:
                        root.after(0, lambda: status_var.set("Safety cutoff activated"))
                        root.after(0, lambda: progress_var.set(0))
                    continue

                if coffeeWaterEnabled:
                    concentrate_duration = duration / (coffeeWaterRatio + 1)

                    if current_pulses <= concentrate_duration:
                        coffee_valve.on()
                        ro_valve.off()
                        if root and concentrate_duration > 0:
                            progress = int((current_pulses / duration) * 100)
                            root.after(0, lambda p=progress: progress_var.set(min(p, 100)))
                            root.after(0, lambda p=progress: status_var.set(f"Dispensing Concentrate... {p}%"))
                        time.sleep(0.25)
                    elif current_pulses < duration:
                        coffee_valve.off()
                        ro_valve.on()
                        if root and duration > 0:
                            progress = int((current_pulses / duration) * 100)
                            root.after(0, lambda p=progress: progress_var.set(min(p, 100)))
                            root.after(0, lambda p=progress: status_var.set(f"Dispensing RO Water... {p}%"))
                        time.sleep(0.25)
                    else:
                        ro_valve.off()
                        coffee_valve.off()
                        with pulse_lock:
                            pulse_count = 0
                        coffeeWaterEnabled = False
                        sleepEnabled = True
                        valve_start_time = None
                        if root:
                            root.after(0, lambda: status_var.set("Ready"))
                            root.after(0, lambda: progress_var.set(0))
                else:
                    ro_valve.on()
                    if root and duration > 0:
                        progress = int((current_pulses / duration) * 100)
                        root.after(0, lambda p=progress: progress_var.set(min(p, 100)))
                        root.after(0, lambda p=progress: status_var.set(f"Dispensing RO Water... {p}%"))
                    time.sleep(0.25)

                    if current_pulses >= duration:
                        ro_valve.off()
                        with pulse_lock:
                            pulse_count = 0
                        drinkWaterEnabled = False
                        sleepEnabled = True
                        valve_start_time = None
                        if root:
                            root.after(0, lambda: status_var.set("Ready"))
                            root.after(0, lambda: progress_var.set(0))

            else:
                if drinkWaterEnabled or coffeeWaterEnabled:
                    ro_valve.off()
                    coffee_valve.off()
                    with pulse_lock:
                        pulse_count = 0
                    drinkWaterEnabled = False
                    coffeeWaterEnabled = False
                    valve_start_time = None
                    if root:
                        root.after(0, lambda: status_var.set("Ready"))
                        root.after(0, lambda: progress_var.set(0))

                deltaTime = time.time() - currentTime
                if deltaTime >= sleepTime:
                    sleepEnabled = True

    except KeyboardInterrupt:
        print("Control loop stopped.")

# ---------------- Button Actions ----------------
def on_button_click(button_number):
    global drinkWaterEnabled, coffeeWaterEnabled, pin, duration, currentTime, sleepEnabled, pulse_count
    sleepEnabled = False
    currentTime = time.time()
    if button_number < 1 or button_number > 6:
        return

    # If dispensing, stop
    if drinkWaterEnabled or coffeeWaterEnabled:
        drinkWaterEnabled = False
        coffeeWaterEnabled = False
        ro_valve.off()
        coffee_valve.off()
        with pulse_lock:
            pulse_count = 0
        if root:
            root.after(0, lambda: status_var.set("Stopped"))
            root.after(0, lambda: progress_var.set(0))
        return

    with pulse_lock:
        pulse_count = 0

    if button_number <= 1:
        drinkWaterEnabled = False
        coffeeWaterEnabled = True
    else:
        coffeeWaterEnabled = False
        drinkWaterEnabled = True

    duration = pulses_needed[button_number - 1]
    if root:
        root.after(0, lambda: status_var.set(f"Dispensing button {button_number}"))

# ---------------- Custom Amount Screen ----------------
def open_custom_screen():
    global sleepEnabled, currentTime
    sleepEnabled = False
    currentTime = time.time()
    custom_win = tk.Toplevel(root)
    custom_win.title("Custom Dispense")
    custom_win.geometry("800x480")
    custom_win.config(bg="black")

    tk.Label(custom_win, text="Custom RO Water Amount",
             fg="white", bg="black", font=("Arial", 20, "bold")).pack(pady=15)

    value_label = tk.Label(custom_win, text="0 ml", fg="cyan", bg="black", font=("Arial", 32, "bold"))
    value_label.pack(pady=10)

    slider = tk.Scale(custom_win, from_=50, to=8000, orient="horizontal", length=700,
                      bg="black", fg="white", troughcolor="gray30", highlightthickness=0,
                      font=("Arial", 12), sliderlength=40, width=20, showvalue=0,
                      command=lambda v: value_label.config(text=f"{int(float(v))} ml"))
    slider.set(500)
    slider.pack(pady=10)

    quick_frame = tk.Frame(custom_win, bg="black")
    quick_frame.pack(pady=15)

    tk.Label(quick_frame, text="Quick Select:", fg="white", bg="black",
             font=("Arial", 16, "bold")).grid(row=0, column=0, columnspan=6, pady=5)

    for idx, l in enumerate([0.25, 0.5, 0.75, 1.0, 1.5, 2.0]):
        tk.Button(quick_frame, text=f"{l} L", font=("Arial", 14), width=6,
                  command=lambda val=l: slider.set(val*1000),
                  bg="gray25", fg="white", activebackground="gray40").grid(row=1, column=idx, padx=3, pady=3)

    for idx, c in enumerate([0.5, 1.0, 1.5, 2.0, 2.5, 3.0]):
        tk.Button(quick_frame, text=f"{c} cup", font=("Arial", 14), width=6,
                  command=lambda val=c*240: slider.set(val),
                  bg="gray25", fg="white", activebackground="gray40").grid(row=2, column=idx, padx=3, pady=3)

    def start_custom_dispense():
        global drinkWaterEnabled, duration, currentTime, sleepEnabled
        sleepEnabled = False
        ml = slider.get()
        duration = (ml / 1000) * Pulses_per_liter_RO
        drinkWaterEnabled = True
        currentTime = time.time()
        custom_win.destroy()
        if root:
            root.after(0, lambda: status_var.set(f"Dispensing {ml:.0f} ml RO Water"))

    button_frame = tk.Frame(custom_win, bg="black")
    button_frame.pack(pady=20)
    tk.Button(button_frame, text="Cancel", font=("Arial", 16), width=12,
              command=custom_win.destroy, bg="gray30", fg="white").pack(side="left", padx=10)
    tk.Button(button_frame, text="Dispense", font=("Arial", 16), width=12,
              command=start_custom_dispense, bg="green", fg="white",
              activebackground="darkgreen").pack(side="left", padx=10)

# ---------------- Calibration Screen ----------------
def open_calibration_screen():
    global sleepEnabled, currentTime, calibration_mode, calibration_start_pulses
    global Pulses_per_liter_RO, Pulses_per_liter_coffee

    sleepEnabled = False
    currentTime = time.time()
    cal_win = tk.Toplevel(root)
    cal_win.title("Calibration")
    cal_win.attributes('-fullscreen', True)
    cal_win.config(bg="black")
    cal_win.config(cursor="none")

    is_running = [False]
    total_pulses = [0]

    main_frame = tk.Frame(cal_win, bg="black")
    main_frame.pack(expand=True, fill="both", padx=10, pady=10)

    tk.Label(main_frame, text="Calibration",
             fg="white", bg="black", font=("Arial", 20, "bold")).pack(pady=5)

    valve_var = tk.StringVar(value="RO")
    valve_frame = tk.Frame(main_frame, bg="black")
    valve_frame.pack(pady=5)
    tk.Radiobutton(valve_frame, text="RO Water", variable=valve_var, value="RO",
                   font=("Arial", 14), bg="black", fg="white", selectcolor="gray30",
                   activebackground="black", indicatoron=False, width=15,
                   relief="raised", borderwidth=2).pack(side="left", padx=5)
    tk.Radiobutton(valve_frame, text="Coffee", variable=valve_var, value="Coffee",
                   font=("Arial", 14), bg="black", fg="white", selectcolor="gray30",
                   activebackground="black", indicatoron=False, width=15,
                   relief="raised", borderwidth=2).pack(side="left", padx=5)

    status_label = tk.Label(main_frame, text="Ready",
                            fg="cyan", bg="black", font=("Arial", 16, "bold"))
    status_label.pack(pady=10)

    pulse_label = tk.Label(main_frame, text="Pulses: 0",
                           fg="white", bg="black", font=("Arial", 28, "bold"))
    pulse_label.pack(pady=5)

    def adjust_entry(entry, delta):
        try:
            new_val = max(1, float(entry.get()) + delta)
            entry.delete(0, tk.END)
            entry.insert(0, str(int(new_val)))
        except ValueError:
            entry.delete(0, tk.END)
            entry.insert(0, "1000")

    target_frame = tk.Frame(main_frame, bg="black")
    target_frame.pack(pady=10)
    tk.Label(target_frame, text="Target (ml):", fg="white", bg="black", font=("Arial", 14)).pack(side="left", padx=5)
    tk.Button(target_frame, text="◄", font=("Arial", 20), width=2,
              command=lambda: adjust_entry(target_entry, -1),
              bg="gray30", fg="white").pack(side="left", padx=2)
    target_entry = tk.Entry(target_frame, font=("Arial", 18), width=8, justify="center",
                            bg="gray20", fg="white", insertbackground="white")
    target_entry.insert(0, "1000")
    target_entry.pack(side="left", padx=2)
    tk.Button(target_frame, text="►", font=("Arial", 20), width=2,
              command=lambda: adjust_entry(target_entry, 1),
              bg="gray30", fg="white").pack(side="left", padx=2)

    actual_frame = tk.Frame(main_frame, bg="black")
    actual_frame.pack(pady=10)
    tk.Label(actual_frame, text="Actual (ml):", fg="yellow", bg="black", font=("Arial", 14)).pack(side="left", padx=5)
    tk.Button(actual_frame, text="◄", font=("Arial", 20), width=2,
              command=lambda: adjust_entry(actual_entry, -1),
              bg="gray30", fg="white").pack(side="left", padx=2)
    actual_entry = tk.Entry(actual_frame, font=("Arial", 18), width=8, justify="center",
                            bg="gray20", fg="white", insertbackground="white")
    actual_entry.insert(0, "1000")
    actual_entry.pack(side="left", padx=2)
    tk.Button(actual_frame, text="►", font=("Arial", 20), width=2,
              command=lambda: adjust_entry(actual_entry, 1),
              bg="gray30", fg="white").pack(side="left", padx=2)

    def update_display():
        if is_running[0]:
            with pulse_lock:
                current = pulse_count - calibration_start_pulses
            pulse_label.config(text=f"Pulses: {current}")
            cal_win.after(100, update_display)

    def start_calibration():
        global drinkWaterEnabled, coffeeWaterEnabled, duration
        global calibration_mode, calibration_start_pulses, pulse_count

        if is_running[0]:
            return
        is_running[0] = True
        calibration_mode = True
        with pulse_lock:
            calibration_start_pulses = pulse_count

        if valve_var.get() == "RO":
            drinkWaterEnabled = True
            coffeeWaterEnabled = False
        else:
            coffeeWaterEnabled = True
            drinkWaterEnabled = False

        duration = 999999
        status_label.config(text="DISPENSING", fg="green")
        stop_btn.config(state="normal", bg="red")
        start_btn.config(state="disabled", bg="gray40")
        calc_btn.config(state="disabled")
        update_display()

    def stop_calibration():
        global drinkWaterEnabled, coffeeWaterEnabled, calibration_mode, pulse_count

        if not is_running[0]:
            return
        is_running[0] = False
        drinkWaterEnabled = False
        coffeeWaterEnabled = False
        calibration_mode = False
        ro_valve.off()
        coffee_valve.off()

        with pulse_lock:
            total_pulses[0] = pulse_count - calibration_start_pulses

        status_label.config(text="Stopped - Enter actual volume", fg="yellow")
        stop_btn.config(state="disabled", bg="gray40")
        start_btn.config(state="normal", bg="green")
        calc_btn.config(state="normal", bg="blue")
        actual_entry.focus()

    def calculate_calibration():
        global Pulses_per_liter_RO, Pulses_per_liter_coffee

        try:
            actual_ml = float(actual_entry.get())
            if actual_ml <= 0:
                status_label.config(text="Error: Volume must be positive", fg="red")
                return

            pulses_per_liter = (total_pulses[0] / actual_ml) * 1000

            if valve_var.get() == "RO":
                Pulses_per_liter_RO = int(pulses_per_liter)
                result_text = f"RO: {Pulses_per_liter_RO} p/L"
            else:
                Pulses_per_liter_coffee = int(pulses_per_liter)
                result_text = f"Coffee: {Pulses_per_liter_coffee} p/L"

            status_label.config(text=result_text, fg="green")

            global pulses_needed
            pulses_needed = calc_pulses_needed()
            save_btn.config(state="normal", bg="orange")

        except ValueError:
            status_label.config(text="Error: Invalid volume", fg="red")

    def save_to_file():
        try:
            with open("/media/edp/SAMDATA/calibration.txt", "w") as f:
                f.write(f"Pulses_per_liter_RO={Pulses_per_liter_RO}\n")
                f.write(f"Pulses_per_liter_coffee={Pulses_per_liter_coffee}\n")
            status_label.config(text="Saved!", fg="green")
            cal_win.after(1500, cal_win.destroy)
        except Exception as e:
            status_label.config(text=f"Save error: {e}", fg="red")

    button_frame = tk.Frame(main_frame, bg="black")
    button_frame.pack(pady=5)

    start_btn = tk.Button(button_frame, text="START", font=("Arial", 14, "bold"),
                          width=12, height=2, command=start_calibration,
                          bg="green", fg="white", activebackground="darkgreen")
    start_btn.grid(row=0, column=0, padx=3, pady=3)

    stop_btn = tk.Button(button_frame, text="STOP", font=("Arial", 14, "bold"),
                         width=12, height=2, command=stop_calibration,
                         bg="gray40", fg="white", state="disabled")
    stop_btn.grid(row=0, column=1, padx=3, pady=3)

    calc_btn = tk.Button(button_frame, text="Calculate", font=("Arial", 14, "bold"),
                         width=12, height=2, command=calculate_calibration,
                         bg="blue", fg="white", activebackground="darkblue")
    calc_btn.grid(row=1, column=0, padx=3, pady=3)

    save_btn = tk.Button(button_frame, text="Save", font=("Arial", 14, "bold"),
                         width=12, height=2, command=save_to_file,
                         bg="gray40", fg="white", state="disabled")
    save_btn.grid(row=1, column=1, padx=3, pady=3)

    tk.Button(main_frame, text="Close", font=("Arial", 12), width=15,
              command=cal_win.destroy, bg="gray30", fg="white").pack(pady=5)

# ---------------- Load Calibration on Startup ----------------
def load_calibration():
    global Pulses_per_liter_RO, Pulses_per_liter_coffee, pulses_needed
    try:
        with open("media/edp/SAMDATA/calibration.txt", "r") as f:
            for line in f:
                if line.startswith("Pulses_per_liter_RO="):
                    Pulses_per_liter_RO = int(line.split("=")[1].strip())
                elif line.startswith("Pulses_per_liter_coffee="):
                    Pulses_per_liter_coffee = int(line.split("=")[1].strip())
        pulses_needed = calc_pulses_needed()
        print(f"Calibration loaded: RO={Pulses_per_liter_RO}, Coffee={Pulses_per_liter_coffee}")
    except FileNotFoundError:
        print("No calibration file found, using defaults")
    except Exception as e:
        print(f"Error loading calibration: {e}")

# ---------------- Settings Screen ----------------
def open_settings_screen():
    global sleepEnabled, currentTime, concentrate_ppm, target_ppm
    sleepEnabled = False
    currentTime = time.time()
    settings_win = tk.Toplevel(root)
    settings_win.title("Settings")
    settings_win.geometry("800x480")
    settings_win.config(bg="black")

    tk.Label(settings_win, text="Concentrate PPM:", fg="white", bg="black", font=("Arial", 16)).pack(pady=10)
    conc_var = tk.IntVar(value=concentrate_ppm)
    tk.Label(settings_win, textvariable=conc_var, font=("Arial", 24), fg="white", bg="black").pack(pady=10)
    conc_frame = tk.Frame(settings_win, bg="black")
    conc_frame.pack()
    tk.Button(conc_frame, text="-", font=("Arial", 32), width=4,
              command=lambda: conc_var.set(max(1, conc_var.get() - 10))).pack(side="left", padx=20)
    tk.Button(conc_frame, text="+", font=("Arial", 32), width=4,
              command=lambda: conc_var.set(conc_var.get() + 10)).pack(side="left", padx=20)

    tk.Label(settings_win, text="Target PPM:", fg="white", bg="black", font=("Arial", 16)).pack(pady=10)
    target_var = tk.IntVar(value=target_ppm)
    tk.Label(settings_win, textvariable=target_var, font=("Arial", 24), fg="white", bg="black").pack(pady=10)
    target_frame = tk.Frame(settings_win, bg="black")
    target_frame.pack()
    tk.Button(target_frame, text="-", font=("Arial", 32), width=4,
              command=lambda: target_var.set(max(1, target_var.get() - 1))).pack(side="left", padx=20)
    tk.Button(target_frame, text="+", font=("Arial", 32), width=4,
              command=lambda: target_var.set(target_var.get() + 1)).pack(side="left", padx=20)

    def save_settings():
        global coffeeWaterRatio, concentrate_ppm, target_ppm
        C = conc_var.get()
        T = target_var.get()
        if T >= C:
            status_var.set("Error: target must be less than concentrate.")
        else:
            concentrate_ppm = C
            target_ppm = T
            coffeeWaterRatio = (C - T) / T
            status_var.set(f"Target {T} ppm set (ratio = {coffeeWaterRatio:.2f})")
            settings_win.destroy()

    tk.Button(settings_win, text="Save", font=("Arial", 18),
              command=save_settings, bg="blue", fg="white").pack(pady=20)

# ---------------- GUI ----------------
def load_image(image_path, width, height):
    img = Image.open(image_path)
    img.thumbnail((width, height), Image.LANCZOS)
    padded = Image.new("RGB", (width, height), (0, 0, 0))
    offset = ((width - img.width) // 2, (height - img.height) // 2)
    padded.paste(img, offset)
    return ImageTk.PhotoImage(padded)

def create_gui():
    global root, status_var, progress_var
    root = tk.Tk()
    root.geometry("800x480")
    root.title("Water Dispenser")
    root.attributes('-fullscreen', True)
    root.config(bg="black")
    root.config(cursor="none")

    image_width, image_height = 250, 200
    image_paths = [
        "/media/edp/SAMDATA/MoccaMaster1L.jpg", "/media/edp/SAMDATA/32ozCup.jpg",
        "/media/edp/SAMDATA/nalgene.jpg", "/media/edp/SAMDATA/kidsCup.jpg",
        "/media/edp/SAMDATA/kidsBottle.jpg", "/media/edp/SAMDATA/BlueCup.jpg"
    ]

    for i in range(6):
        img = load_image(image_paths[i], image_width, image_height)
        button = tk.Button(root, image=img, command=lambda i=i: on_button_click(i+1))
        button.image = img
        button.grid(row=i//3, column=i%3, padx=2, pady=2)

    progress_var = tk.IntVar()
    ttk.Progressbar(root, variable=progress_var, maximum=100).grid(
        row=2, column=0, columnspan=3, sticky="we", padx=2, pady=2)

    status_var = tk.StringVar(value="Ready")
    tk.Label(root, textvariable=status_var, bd=1, relief="sunken", anchor="w",
             font=("Arial", 14), bg="black", fg="white").grid(
        row=3, column=0, sticky="we", padx=2, pady=2)

    tk.Button(root, text="Custom", font=("Arial", 12), bg="gray20", fg="white",
              command=open_custom_screen).grid(row=3, column=1, sticky="we", padx=2, pady=2)

    settings_btn = tk.Button(root, text="Settings", font=("Arial", 12), bg="gray20", fg="white",
                             command=open_settings_screen)
    settings_btn.grid(row=3, column=2, sticky="we", padx=2, pady=2)

    press_time = [0]
    def on_press(e):
        press_time[0] = time.time()
    def on_release(e):
        if time.time() - press_time[0] >= 2.0:
            open_calibration_screen()
        else:
            open_settings_screen()
    settings_btn.bind("<ButtonPress-1>", on_press)
    settings_btn.bind("<ButtonRelease-1>", on_release)
    settings_btn.config(command=None)

    root.mainloop()

# ---------------- Start ----------------
try:
    load_calibration()
    gpio_thread = threading.Thread(target=control_gpio, daemon=True)
    gpio_thread.start()
    create_gui()
finally:
    ro_valve.off()
    coffee_valve.off()
    ro_valve.close()
    coffee_valve.close()
    flow_sensor.close()