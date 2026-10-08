import tkinter as tk
import datetime

# ============================================================
# TRASH + RECYCLING COLLECTION SETUP
# ============================================================

# The first recycling pickup date
RECYCLING_START_DATE = datetime.date(2026,10, 12)

# Pickup weekday: 0 = Monday ... 6 = Sunday
PICKUP_WEEKDAY = 0

# How often (ms) to re-raise the window so nothing can sit on top of it
RAISE_INTERVAL_MS = 500


# ============================================================
# DETERMINE TODAY AND NEXT PICKUP
# ============================================================

TODAY = datetime.date.today()

# Days until the next pickup (0 if today IS pickup day)
days_until_pickup = (PICKUP_WEEKDAY - TODAY.weekday()) % 7
NEXT_PICKUP_DATE = TODAY + datetime.timedelta(days=days_until_pickup)


# ============================================================
# DETERMINE WHETHER PICKUP IS RECYCLING WEEK
# ============================================================

def is_recycling_pickup(pickup_date):
    """Recycling occurs every other pickup, starting with RECYCLING_START_DATE."""
    weeks_since_start = (pickup_date - RECYCLING_START_DATE).days // 7
    return weeks_since_start % 2 == 0


# ============================================================
# DISPLAY WARNING
# ============================================================

def show_warning(message, bg_color):
    root = tk.Tk()
    root.title("Waste Collection Reminder")
    root.configure(background=bg_color)

    # Fullscreen and always on top
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)

    label = tk.Label(
        root,
        text=message,
        font=("DejaVu Sans", 56, "bold"),
        fg="white",
        bg=bg_color,
        wraplength=root.winfo_screenwidth() - 100,
        justify="center",
    )
    label.pack(expand=True)

    dismiss_button = tk.Button(
        root,
        text="Dismiss",
        font=("DejaVu Sans", 24, "bold"),
        fg="white",
        bg="black",
        activebackground="gray",
        activeforeground="white",
        padx=40,
        pady=20,
        command=root.destroy,
    )
    dismiss_button.pack(pady=40)

    # Escape also dismisses
    root.bind("<Escape>", lambda e: root.destroy())

    # Take focus so the window is actually in front
    root.update()
    root.lift()
    root.focus_force()

    # Some window managers let other windows reclaim the top spot,
    # so keep re-asserting it until dismissed.
    def keep_on_top():
        root.attributes("-topmost", True)
        root.lift()
        root.after(RAISE_INTERVAL_MS, keep_on_top)

    root.after(RAISE_INTERVAL_MS, keep_on_top)

    root.mainloop()


# ============================================================
# MAIN PROGRAM
# ============================================================

if __name__ == "__main__":

    recycling = is_recycling_pickup(NEXT_PICKUP_DATE)
    reminder_day = (PICKUP_WEEKDAY - 1) % 7

    if TODAY.weekday() == reminder_day:
        if recycling:
            show_warning("REMINDER:\nTOMORROW IS RECYCLING DAY!", bg_color="green")
        else:
            show_warning("REMINDER:\nTOMORROW IS TRASH DAY!", bg_color="blue")

    elif TODAY.weekday() == PICKUP_WEEKDAY:
        if recycling:
            show_warning("TODAY IS RECYCLING DAY!", bg_color="green")
        else:
            show_warning("TODAY IS TRASH DAY!", bg_color="blue")
