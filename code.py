print("Hello World!")
import wifi
import socketpool
import ssl
import adafruit_requests
import json
import os
import time
import supervisor

supervisor.runtime.autoreload = False

SHA_STORE = "/.file_shas.json"   # persisted on flash
GITHUB_USER = "initnc"
GITHUB_REPO = "circpy"
BRANCH      = "main"
GIT_LOOKUP_TIMESTAMP = None

def main():
    wificheck = check_wifi()
    if wificheck==True:
        pool = socketpool.SocketPool(wifi.radio)
        ctx  = ssl.create_default_context()
        session = adafruit_requests.Session(pool, ctx)
        
        while True:
            checkrepo = check_git_lookup_timestamp()
            if checkrepo == True:
                check_for_updates(session)
            else:
                print("not enough time has passed")
        
def check_wifi():
    print("checking wifi status")
    if not wifi.radio.connected:
        raise RuntimeError("WiFi not connected — check settings.toml")
        return False
    else:
        print(f"IP: {wifi.radio.ipv4_address}")
        return True

def load_sha_store():
    print("loading sha from store")
    try:
        with open(SHA_STORE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def save_sha_store(shas):
    print("saving new sha from repo")
    """
    with open(SHA_STORE, "w") as f:
        json.dump(shas, f)
    """

def get_tree_shas(session):
    print("fetching tree from repo")
    # Step 1: get the SHA of the HEAD commit
    url = (
        f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}"
        f"/git/ref/heads/{BRANCH}"
    )
    headers = {"Accept": "application/vnd.github.v3+json",
               "User-Agent": "pico-updater"}
    
    r = session.get(url, headers=headers)
    commit_sha = r.json()["object"]["sha"]
    r.close()

    # Step 2: get the tree for that commit (recursive = all files at once)
    url = (
        f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}"
        f"/git/trees/{commit_sha}?recursive=1"
    )
    r = session.get(url, headers=headers)
    tree = r.json()["tree"]
    r.close()

    # Build a dict of { repo_path: sha }
    return {item["path"]: item["sha"] for item in tree if item["type"] == "blob"}

def download_file(session, repo_path, local_path):
    url = (
        f"https://raw.githubusercontent.com/{GITHUB_USER}"
        f"/{GITHUB_REPO}/{BRANCH}/{repo_path}"
    )
    headers = {"User-Agent": "pico-updater"}
    r = session.get(url, headers=headers)
    if r.status_code != 200:
        print(f"  Download failed ({r.status_code}) for {repo_path}")
        r.close()
        return False

    # Make sure intermediate dirs exist
    parts = local_path.rsplit("/", 1)
    if len(parts) == 2:
        try:
            os.mkdir(parts[0])
        except OSError:
            pass  # already exists

    """
    with open(local_path, "w") as f:
        f.write(r.text)
    """
    r.close()
    print(f"  ✓ Updated {local_path}")
    return True

def check_for_updates(session):
    local_shas = load_sha_store()
    remote_shas = get_tree_shas(session)
    updated = False

    for repo_path, remote_sha in remote_shas.items():
        if local_shas.get(repo_path) != remote_sha:
            print(f"  {repo_path} changed — downloading...")
            if download_file(session, repo_path, repo_path):  # same path locally
                local_shas[repo_path] = remote_sha
                updated = True
        else:
            print(f"  {repo_path} up to date")

    if updated:
        save_sha_store(local_shas)
        import supervisor
        supervisor.reload()

def check_git_lookup_timestamp():
    global GIT_LOOKUP_TIMESTAMP
    if GIT_LOOKUP_TIMESTAMP != None:
        now = time.time()
        delta_t = now - GIT_LOOKUP_TIMESTAMP
        if delta_t > 120:
            GIT_LOOKUP_TIMESTAMP = now
            return True
        else:
            return False
    else:
        GIT_LOOKUP_TIMESTAMP = time.time()
        return True



if __name__ == "__main__":
    main()
