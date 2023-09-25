import copy
import io
import json
import shutil
import tempfile
import urllib3
import zipfile
from dataclasses import dataclass, field
from functools import partial
from htmllistparse import fetch_listing
from pathlib import Path
from platformdirs import user_config_dir
from utils import hash
from multiprocessing.pool import ThreadPool


@dataclass
class Diff:
    new_list: list = field(default_factory=list)
    replace_list: list = field(default_factory=list)
    remove_list: list = field(default_factory=list)
    ignore_list: list = field(default_factory=list)


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
        "pool_limit": 12,
        "new_install_threshold": 1000,
        "install_dir": "",
        "install_dir_tips": "为了与GUI版本保持兼容",
        "dir_name": "mower",
        "mower_tips": "为了与GUI版本保持兼容",
    }


    def __init__(self, conf_path: str | None = None):
        self.conf_path: Path = Path(conf_path) if conf_path else Path(user_config_dir("mower_updater", ensure_exists=True)) / 'config.json'
        self.tmp_dir: Path = Path(tempfile.gettempdir()) / 'mower_updater'
        self.conf = None
        self.http = None
        self.cache = {}


    def __destroy__(self):
        self._save_conf()


    def _load_conf(self):
        default_conf = copy.deepcopy(Updater.default_config)
        if self.conf_path.exists():
            with self.conf_path.open('r') as f:
                conf = json.load(f)
                default_conf.update(conf)
        self.conf = default_conf
        
        self.http = urllib3.PoolManager(self.conf['pool_limit'])


    def _save_conf(self):
        with self.conf_path.open('w') as f:
            json.dump(self.conf, f)


    def connect_mirror(self, mirror: str = None):
        mirror = mirror if mirror else self.conf['mirror']
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


    def fetch_version_details(self, versions, mirror: str = None):
        mirror = mirror if mirror else self.conf['mirror']
        if not mirror.endswith("/"):
            mirror += "/"
        result = []
        for v in versions:
            url = mirror + v + "/version.json"
            try:
                resp = self.http.request('GET', url)
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
        self.cache['versions'] = result
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
            elif f not in diff.ignore_list:
                diff.new_list.append(f)
        for f, h in old_hash.items():
            if f not in new_hash and f not in diff.ignore_list:
                diff.remove_list.append(f)
                
        return diff


    def download_file(self, ver_name, subpath, mirror: str = None):
        path = self.tmp_dir / ver_name / subpath
        if path.exists():
            return # 之前下载过的文件不需要再下载
        
        mirror = mirror if mirror else self.conf['mirror']
        url = f"{mirror}/{ver_name}/{subpath}" # 保持mirror没有结尾斜杠。应该由配置设置方来保证

        # TCP协议在底层已经包含了重传，requests中也有retries相关的定义
         # 因此如果抛出异常，基本表明下载就是失败了，应该原路回退到调用方为止
        resp = self.http.request('GET', url)
        path.parent.mkdir(exist_ok=True, parents=True)
        with path.open("wb") as f:
            f.write(resp.data)
        return path


    def download_all_files(self, ver_name, diff: Diff, callback = None, mirror: str = None):
        mirror = mirror if mirror else self.conf['mirror']
        remains = len(diff.new_list) + len(diff.replace_list)
        partial_download = partial(self.download_file, ver_name)
        with ThreadPool(self.conf["pool_limit"]) as pool:
            for subpath in pool.imap_unordered(
                partial_download, diff.new_list + diff.replace_list
            ):
                remains -= 1
                if callback:
                    callback(remains, str(subpath))
    
    
    def remove_old_files(self, path):
        path = Path(path)
        ignore_list = []
        
        for pattern in self.conf['ignores']:
            for file in path.glob(pattern):
                ignore_list.append(file)
        
        for file in path.glob('**/*'):
            if file not in ignore_list:
                file.unlink()
    

    def remove_files(self, path, diff: Diff):
        path = Path(path)
        failed_list = []
        for subpath in diff.remove_list:
            path = path / subpath
            try:
                path.unlink()
            except Exception as e:
                failed_list.append({"path": path, "reason": str(e)})
        return failed_list
    
    
    def perform_install(self, ver_name, install_path, diff: Diff):
        self.remove_files(install_path, diff)
        install_path = Path(install_path)
        install_path.parent.mkdir(exist_ok=True, parents=True)
        new_ver_dir: Path = self.tmp_dir / ver_name
        for item in new_ver_dir.iterdir():
            shutil.copy(str(item), str(install_path))
    
    
    def install(self, ver_name, install_path):
        install_path = Path(install_path)
        mirror_status = self.connect_mirror()
        if mirror_status['status_code'] != 0:
            raise mirror_status['exception']

        versions = self.cache.get('versions')
        if not versions:
            versions = self.fetch_version_details()
        
        try:
            target_version = next(filter(lambda v: v['version'] == ver_name, versions))
        except:
            raise RuntimeError('没有找到目标版本')
        
        if not install_path.exists() or not any(install_path.iterdir()):
            self.new_install(ver_name, install_path)
            return
        
        diff = self.get_diff(install_path, target_version['hash'])
        
        if len(diff.new_list) >= self.conf['new_install_threshold']:
            # too many files to download; perform new_install
            self.new_install(ver_name, install_path)
            return
        
        self.download_all_files(ver_name, diff)
        self.perform_install(ver_name, install_path, diff)
        
    
    def new_install(self, ver_name, install_path):
        install_path = Path(install_path)
        self.remove_old_files(install_path)
        
        mirror = self.conf['mirror']
        url = f"{mirror}/{ver_name}.zip"
        resp = self.http.request('GET', url)
        zip_data = io.BytesIO(resp.data)
        with zipfile.ZipFile(zip_data) as zf:
            zf.extractall(install_path.parent)
        
        shutil.move(install_path.parent / ver_name, install_path)

        

