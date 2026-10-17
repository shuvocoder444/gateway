import os
import sys
import zipfile
import paramiko
import time
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except Exception:
        pass

HOST = "195.250.26.201"
PORT = 22
USERNAME = "webkoders"
KEY_PATH = "C:/Users/shuvo/.ssh/id_rsa"
REMOTE_BASE = "/home/webkoders/payment.webkoders.com"
LOCAL_BASE = r"d:\gateway"
PY_BIN = "/home/webkoders/virtualenv/payment.webkoders.com/3.12/bin/python"
PIP_BIN = "/home/webkoders/virtualenv/payment.webkoders.com/3.12/bin/pip"

IGNORE_DIRS = {".git", ".vscode", "venv", "__pycache__", ".venv", ".idea", "staticfiles", "media"}
IGNORE_FILES = {"deploy_package.zip", ".DS_Store", "deploy_to_cpanel.py", "db.sqlite3"}

def create_archive():
    zip_path = os.path.join(LOCAL_BASE, "deploy_package.zip")
    print(f"[*] Packaging project into {zip_path}...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(LOCAL_BASE):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for f in files:
                if (f in IGNORE_FILES or f.endswith(".pyc") or f.endswith(".tmp")
                        or f == ".env" or f.startswith(".env.")):
                    continue
                filepath = os.path.join(root, f)
                arcname = os.path.relpath(filepath, LOCAL_BASE)
                zipf.write(filepath, arcname)
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[+] Archive ready: {size_mb:.2f} MB")
    return zip_path

def run_cmd(ssh, cmd):
    print(f"[*] Executing: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(f"    [STDOUT]\n{out.strip()}")
    if err.strip():
        print(f"    [STDERR]\n{err.strip()}")
    return code, out, err

def deploy():
    zip_path = create_archive()

    print("[*] Connecting via SSH to 195.250.26.201...")
    passphrase = os.environ.get("CPANEL_SSH_KEY_PASSPHRASE")
    if not passphrase:
        sftp_json_path = os.path.join(LOCAL_BASE, ".vscode", "sftp.json")
        if os.path.exists(sftp_json_path):
            import json
            try:
                with open(sftp_json_path, "r", encoding="utf-8") as f:
                    passphrase = json.load(f).get("passphrase")
            except Exception:
                pass
    if not passphrase:
        raise RuntimeError("Set CPANEL_SSH_KEY_PASSPHRASE or define passphrase in .vscode/sftp.json before deploying.")
    key = paramiko.RSAKey.from_private_key_file(KEY_PATH, password=passphrase)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USERNAME, pkey=key, port=PORT, timeout=30, banner_timeout=60)
    print("[+] SSH Connected successfully!")

    sftp = ssh.open_sftp()
    try:
        remote_zip = f"{REMOTE_BASE}/deploy_package.zip"
        print(f"[*] Uploading {zip_path} -> {remote_zip} via SFTP...")
        sftp.put(zip_path, remote_zip)
        print("[+] Upload complete!")

        print("\n[*] Unzipping package on remote server...")
        code, _, _ = run_cmd(ssh, f"unzip -o {remote_zip} -d {REMOTE_BASE} && rm -f {remote_zip}")
        if code:
            raise RuntimeError("Remote extraction failed; deployment stopped.")

        print("\n[*] Installing project dependencies...")
        code, _, _ = run_cmd(ssh, f"cd {REMOTE_BASE} && {PIP_BIN} install -r requirements.txt")
        if code:
            raise RuntimeError("Dependency installation failed; deployment stopped.")

        print("\n[*] Ensuring permissions on sqlite database...")
        run_cmd(ssh, f"chmod 664 {REMOTE_BASE}/db.sqlite3 2>/dev/null || true")

        print("\n[*] Running Django migrations...")
        code, _, _ = run_cmd(ssh, f"cd {REMOTE_BASE} && {PY_BIN} manage.py migrate --noinput")
        if code:
            raise RuntimeError("Database migration failed; deployment stopped.")

        print("\n[*] Collecting static files...")
        code, _, _ = run_cmd(ssh, f"cd {REMOTE_BASE} && {PY_BIN} manage.py collectstatic --noinput")
        if code:
            raise RuntimeError("Static file collection failed; deployment stopped.")

        print("\n[*] Restarting Phusion Passenger...")
        code, _, _ = run_cmd(ssh, f"mkdir -p {REMOTE_BASE}/tmp && touch {REMOTE_BASE}/tmp/restart.txt")
        if code:
            raise RuntimeError("Passenger restart signal failed.")
        print("[+] Touched tmp/restart.txt!")

    finally:
        sftp.close()
        ssh.close()

    print("\n[*] Verifying live endpoints...")
    time.sleep(3)
    urls = [
        "https://payment.webkoders.com/admin-dashboard/",
        "https://payment.webkoders.com/dashboard/",
        "https://payment.webkoders.com/api/v1/device/sync-sms/",
        "https://payment.webkoders.com/download/sms-forwarder/",
        "https://payment.webkoders.com/download/sms-forwarder-source/",
    ]
    verification_issues = []
    for url in urls:
        try:
            method = requests.head if '/download/' in url else requests.get
            r = method(url, timeout=15, allow_redirects=False)
            print(f"  [HTTP {r.status_code}] {url}")
            if r.status_code >= 500:
                verification_issues.append(f"HTTP {r.status_code}: {url}")
        except Exception as e:
            print(f"  [ERR] {url} -> {e}")
            verification_issues.append(f"{url}: {e}")

    if verification_issues:
        print("[!] Deployment completed, but one or more endpoint checks need another look.")

    print("\n" + "=" * 60)
    print("  Deployment Finished!")
    print("  Live URL: https://payment.webkoders.com/admin-dashboard/")
    print("=" * 60)

if __name__ == "__main__":
    deploy()
