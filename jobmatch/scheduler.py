import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from jobmatch.config import home, settings

TASK_NAME = "JobMatchLocalAI-Sync"


def task_xml():
    hours = settings().interval_hours
    python = Path(sys.executable).with_name("pythonw.exe")
    user = subprocess.check_output(["whoami"], text=True).strip()
    args = f'-m jobmatch.cli --data-dir "{home()}" sync'
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<Triggers><LogonTrigger><Repetition><Interval>PT{hours}H</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><Enabled>true</Enabled><UserId>{escape(user)}</UserId></LogonTrigger></Triggers>
<Principals><Principal id="Author"><UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT0S</ExecutionTimeLimit></Settings>
<Actions Context="Author"><Exec><Command>{escape(str(python))}</Command><Arguments>{escape(args)}</Arguments><WorkingDirectory>{escape(str(Path(__file__).resolve().parent.parent))}</WorkingDirectory></Exec></Actions>
</Task>"""


def install():
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as file:
        path = Path(file.name)
    try:
        path.write_text(task_xml(), encoding="utf-16")
        subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(path), "/F"],
            check=True,
            capture_output=True,
        )
    finally:
        path.unlink(missing_ok=True)


def remove():
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=True, capture_output=True
    )
