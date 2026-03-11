import subprocess
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    pid: int
    name: str
    bundle_id: str


def list_gui_apps() -> list[ProcessInfo]:
    """実行中のGUIアプリ一覧を取得する"""
    script = '''
    tell application "System Events"
        set appList to every application process whose visible is true
        set output to ""
        repeat with proc in appList
            set output to output & (unix id of proc) & "|||" & (name of proc) & "|||" & (bundle identifier of proc) & linefeed
        end repeat
    end tell
    return output
    '''
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            logger.warning(f"osascript エラー: {result.stderr}")
            return _fallback_list()

        processes = []
        for line in result.stdout.strip().split('\n'):
            if '|||' not in line:
                continue
            parts = line.strip().split('|||')
            if len(parts) >= 3:
                try:
                    processes.append(ProcessInfo(
                        pid=int(parts[0].strip()),
                        name=parts[1].strip(),
                        bundle_id=parts[2].strip(),
                    ))
                except ValueError:
                    continue
        return sorted(processes, key=lambda p: p.name)
    except Exception as e:
        logger.warning(f"アプリ一覧取得失敗: {e}")
        return _fallback_list()


def _fallback_list() -> list[ProcessInfo]:
    """AppleScriptが使えない場合のフォールバック"""
    try:
        result = subprocess.run(
            ['ps', '-eo', 'pid,comm'],
            capture_output=True, text=True, timeout=5
        )
        processes = []
        known_apps = {
            'Google Chrome', 'Safari', 'Firefox', 'Arc',
            'Microsoft Edge', 'Brave Browser', 'Opera',
            'VLC', 'Spotify', 'Music', 'QuickTime Player',
        }
        for line in result.stdout.strip().split('\n')[1:]:
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                pid_str, comm = parts
                app_name = comm.split('/')[-1]
                if any(k.lower() in app_name.lower() for k in known_apps):
                    try:
                        processes.append(ProcessInfo(
                            pid=int(pid_str),
                            name=app_name,
                            bundle_id="",
                        ))
                    except ValueError:
                        continue
        return sorted(processes, key=lambda p: p.name)
    except Exception:
        return []
