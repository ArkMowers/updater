import json
import copy
import requests
import xxhash
from urllib3 import PoolManager
from urllib3.util import Retry
from functools import partial
from dataclasses import dataclass
from htmllistparse import fetch_listing
from utils import hash
from platformdirs import user_config_dir, user_cache_dir
from pathlib import Path
from multiprocessing.pool import ThreadPool
from multiprocessing.queues import Queue


@dataclass
class Diff:
    new_list: list
    replace_list: list
    remove_list: list
    ignore_list: list


class Updater:
    default_config = {
        "mirror": "https://mower.zhaozuohong.vip",
        "code": [
            "arknights_mower/__init__/data/**/*",
            "arknights_mower/__init__/solvers/**/*",
            "arknights_mower/__init__/templates/**/*",
            "arknights_mower/__init__/ocr/**/*"
        ],
        "code_tips": [
            "code列表中的内容是所有经常变更的内容，具有较强的时效性",
            "code列表的内容会在发布时打包为zip，以减少传输量，保证版本变更一致性"
        ],
        "resources": [
            "当前版本这是一个无效的参数",
            "因为既不在ignores也不在code中的文件自动成为resources"
        ],
        "resources_tips": [
            "resources列表的内容会在发布时与上个版本进行差异比较"
        ],
        "ignores": [
            "*.yml",
            "*.json",
            "tmp/*",
            "log/*",
            "screenshot/**/*",
            "adb-buildin/*"
        ],
        "pool_limit": 12
    }


    def __init__(self, conf_path: str | None):
        self.conf_path = Path(conf_path) if conf_path else Path(user_config_dir("mower_updater", ensure_exists=True)) / 'config.json'
        self.tmp_dir = Path(user_cache_dir("mower_updater", ensure_exists=True))
        self.conf = None
        self.cache = {}
        self.sess_pool: PoolManager = None


    def __destroy__(self):
        pass


    def _load_conf(self):
        default_conf = copy.deepcopy(Updater.default_config)
        if self.conf_path.exists():
            with self.conf_path.open('r') as f:
                conf = json.load(f)
                default_conf.update(conf)
        self.conf = default_conf
        
        self.sess_pool = PoolManager(self.conf['pool_limit'], )


    def connect_mirror(self, mirror):
        try: # fetch_listing会retry吗？可能需要添加retry
            cwd, listing = fetch_listing(mirror, timeout=30)
            return {
                "status_code": 0,
                "versions": [v.name[:-1] for v in listing if v.name.endswith("/")],
            }
        except Exception as e:
            return {
                "status_code": -1,
                "msg": str(e),
                "exception": e,
            }


    def fetch_version_details(self, mirror, versions):
        if not mirror.endswith("/"):
            mirror += "/"
        result = []
        for v in versions:
            url = mirror + v + "/version.json"
            try:
                resp = requests.get(url)
                resp_json = resp.json()
                pub_time = resp_json["time"]
            except Exception as e:
                continue
            result.append(
                {
                    "version": v,
                    "display_name": f"{v} ({pub_time})",
                    "hash": resp_json["hash"],
                }
            )
        return result


    def get_diff(self, path, new_hash)->Diff:
        path = Path(path)
        diff = Diff()
        if not path.exists():
            for file in new_hash:
                diff.new_list.append(file)
            return diff
        
        for pattern in self.conf['ignores']:
            for file in path.glob(pattern):
                diff.ignore_list.append(str(file)[len(str(path)) + 1 :].replace("\\", "/"))

        old_hash = None
        ver_file = path / 'version.json'
        if ver_file.exists():
            with ver_file.open('r') as f:
                old_ver_info = json.load(f)
                old_hash = old_ver_info['hash']
        else:
            old_hash = hash(path)
        
        for f, h in new_hash.items():
            if f in old_hash:
                if old_hash[f] != h and f not in diff.ignore_list:
                    diff.replace_list.append(f)
            elif f not in ignore_list:
                diff.new_list.append(f)
        for f, h in old_hash.items():
            if f not in new_hash and f not in diff.ignore_list:
                diff.remove_list.append(f)

        return diff
    

    def remove_files(self, path, diff: Diff):
        if isinstance(path, str):
            path = Path(path)
        failed_list = []
        for subpath in diff.remove_list:
            path = path / subpath
            try:
                path.unlink()
            except Exception as e:
                failed_list.append({"path": path, "reason": str(e)})
        return failed_list
    

    def get_session(self, mirror)->requests.Session:
        sess = None
        if self.sess_count < self.conf['pool_limit']:
            self.sess_count += 1
            sess = requests.Session()
            return sess
        else:
            return self.sess_pool[mirror].get()


    def release_session(self, mirror, sess):
        self.sess_pool[mirror].put(sess)


    def download_file(self, mirror, ver_name, subpath):
        if not mirror.endswith("/"):
            mirror += "/"
        url = f"{mirror}{ver_name}/{subpath}"

        sess = self.get_session(mirror)
        try:
            resp = sess.get(url)
            path = self.tmp_dir / ver_name / subpath
            path.parent.mkdir(exist_ok=True, parents=True)
            with path.open("wb") as f:
                f.write(resp.content)
        finally:
            self.release_session(sess)

    def download_all_files(self, mirror, ver_name, diff: Diff, callback):
        remains = len(diff.new_list) + len(diff.replace_list)
        partial_download = partial(self.download_file, mirror, ver_name)
        with ThreadPool(self.conf["pool_limit"]) as pool:
            for subpath in pool.imap_unordered(
                partial_download, diff.new_list + diff.replace_list
            ):
                remains -= 1
                callback(remains)
    
    def install(self, ver_name, path):
        mirror = self.conf['mirror']
        mirror_status = self.connect_mirror(mirror)
        if mirror_status['status_code'] != 0:
            raise mirror_status['exception']

        versions = self.cache.get('versions')
        if not versions:
            versions = self.cache['versions'] = self.fetch_version_details()
        if len(versions) == 0:
            raise 
        

        

