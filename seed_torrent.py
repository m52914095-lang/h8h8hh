#!/usr/bin/env python3
"""
Torrent Seeder Script for GitHub Actions
Downloads and seeds a torrent to a target ratio
"""

import libtorrent as lt
import time
import os
import sys
import signal
import tempfile
import shutil
import warnings

# Suppress deprecation warnings for cleaner output
warnings.filterwarnings("ignore", category=DeprecationWarning)

# Configuration
MAGNET_LINK = os.environ.get('MAGNET_LINK', '')
TARGET_RATIO = float(os.environ.get('TARGET_RATIO', '8.0'))
SAVE_DIR = os.environ.get('SAVE_DIR', './torrent_data')
TORRENT_FILE = os.environ.get('TORRENT_FILE', '')
MAX_RUNTIME = int(os.environ.get('MAX_RUNTIME', '19800'))  # 5.5 hours default

# Info hash for this torrent
INFO_HASH = '556fc79fec8ea92c32df2cc2833a573a30b07e84'

# Full magnet with trackers
DEFAULT_MAGNET = f"magnet:?xt=urn:btih:{INFO_HASH}&dn=Detective%20Conan%201201%20(2160)%20by%20DCAIM%20%7BTags%3AL0%3BV15%3BC1%3BA%3Dja%3BS%3Den%3B%7D&tr=https%3A%2F%2Ftracker.nekobt.to%2Fapi%2Ftracker%2Fpublic%2Fannounce&tr=http%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=udp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=udp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&tr=udp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.openbittorrent.com%3A6969%2Fannounce&tr=udp%3A%2F%2Ftracker.moeking.me%3A6969%2Fannounce"

running = True
session = None
handle = None

def signal_handler(sig, frame):
    global running
    print("\n[INFO] Shutdown signal received...")
    running = False

def cleanup():
    global session, handle
    print("[INFO] Cleaning up...")
    if session and handle:
        try:
            session.remove_torrent(handle)
        except Exception as e:
            print(f"[WARN] Cleanup error: {e}")
    print("[INFO] Cleanup complete")

def get_torrent_info():
    """Get torrent info from magnet or torrent file"""
    ses = lt.session()
    
    if TORRENT_FILE and os.path.exists(TORRENT_FILE):
        print(f"[INFO] Loading torrent file: {TORRENT_FILE}")
        with open(TORRENT_FILE, 'rb') as f:
            return lt.torrent_info(f.read())
    
    # Use magnet link
    magnet = MAGNET_LINK if MAGNET_LINK else DEFAULT_MAGNET
    print(f"[INFO] Getting metadata from magnet...")
    
    atp = lt.parse_magnet_uri(magnet)
    atp.save_path = tempfile.mkdtemp()
    
    h = ses.add_torrent(atp)
    
    print("[INFO] Waiting for metadata (max 5 minutes)...")
    timeout = 300
    start = time.time()
    
    while not h.status().has_metadata:
        if time.time() - start > timeout:
            print("[ERROR] Timeout waiting for metadata")
            ses.remove_torrent(h)
            sys.exit(1)
        time.sleep(2)
        elapsed = int(time.time() - start)
        print(f"\r[INFO] Fetching metadata... {elapsed}s", end="", flush=True)
    
    print("\n[INFO] Metadata received!")
    
    # Use torrent_file() instead of deprecated get_torrent_info()
    try:
        ti = h.torrent_file()
    except AttributeError:
        # Fallback for older libtorrent versions
        ti = h.get_torrent_info()
    
    ses.remove_torrent(h)
    
    # Cleanup temp dir
    try:
        shutil.rmtree(atp.save_path)
    except:
        pass
    
    return ti

def download_torrent(ti, save_dir, max_time):
    """Download torrent if not already complete"""
    magnet = MAGNET_LINK if MAGNET_LINK else DEFAULT_MAGNET
    
    os.makedirs(save_dir, exist_ok=True)
    
    ses = lt.session()
    ses.add_dht_router("router.bittorrent.com", 6881)
    ses.add_dht_router("router.utorrent.com", 6881)
    ses.add_dht_router("dht.transmissionbt.com", 6881)
    ses.start_dht()
    
    atp = lt.parse_magnet_uri(magnet)
    atp.save_path = save_dir
    atp.ti = ti
    
    h = ses.add_torrent(atp)
    
    print(f"[INFO] Downloading to: {save_dir}")
    print(f"[INFO] File: {ti.name()}")
    print(f"[INFO] Size: {ti.total_size() / 1024 / 1024:.2f} MB")
    
    start = time.time()
    
    while running and (time.time() - start) < max_time:
        status = h.status()
        
        if status.is_seeding:
            print(f"\n[INFO] Download complete! Time: {time.strftime('%H:%M:%S', time.gmtime(time.time() - start))}")
            return ses, h
        
        progress = status.progress * 100
        dl_rate = status.download_rate / 1024
        peers = status.num_peers
        
        print(f"\r[INFO] Progress: {progress:.1f}% | DL: {dl_rate:.0f} KB/s | Peers: {peers}    ", end="", flush=True)
        time.sleep(2)
    
    if not running:
        print("\n[INFO] Download interrupted")
    else:
        print("\n[INFO] Max runtime reached during download")
    
    return ses, h

def seed_torrent(ti, save_dir, target_ratio, max_time):
    """Seed torrent until target ratio is reached"""
    magnet = MAGNET_LINK if MAGNET_LINK else DEFAULT_MAGNET
    
    ses = lt.session()
    ses.add_dht_router("router.bittorrent.com", 6881)
    ses.add_dht_router("router.utorrent.com", 6881)
    ses.add_dht_router("dht.transmissionbt.com", 6881)
    ses.start_dht()
    
    atp = lt.parse_magnet_uri(magnet)
    atp.save_path = save_dir
    atp.ti = ti
    atp.flags = lt.torrent_flags.seed_mode
    
    h = ses.add_torrent(atp)
    
    file_size = ti.total_size()
    print(f"[INFO] Seeding: {ti.name()}")
    print(f"[INFO] Target ratio: {target_ratio}x ({file_size * target_ratio / 1024 / 1024:.0f} MB)")
    print("-" * 60)
    
    start_time = time.time()
    
    while running and (time.time() - start_time) < max_time:
        status = h.status()
        
        uploaded_mb = status.total_upload / 1024 / 1024
        ratio = status.total_upload / file_size if file_size > 0 else 0
        elapsed = time.strftime('%H:%M:%S', time.gmtime(time.time() - start_time))
        up_rate = status.upload_rate / 1024
        
        print(f"[{time.strftime('%H:%M:%S')}] Upload: {uploaded_mb:.2f} MB | Ratio: {ratio:.3f}x | "
              f"Rate: {up_rate:.0f} KB/s | Peers: {status.num_peers} | Elapsed: {elapsed}")
        
        if ratio >= target_ratio:
            print("\n" + "=" * 60)
            print(f"[SUCCESS] Target ratio {target_ratio}x reached!")
            print(f"[SUCCESS] Total uploaded: {uploaded_mb:.2f} MB")
            print(f"[SUCCESS] Final ratio: {ratio:.3f}x")
            break
        
        time.sleep(60)
    
    if not running:
        print("\n[INFO] Seeding interrupted by signal")
    elif (time.time() - start_time) >= max_time:
        print("\n[INFO] Max runtime reached, will continue in next run")
    
    return ses, h

def main():
    global running, session, handle
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("=" * 60)
    print("TORRENT SEEDER - GitHub Actions")
    print("=" * 60)
    print(f"[INFO] Target ratio: {TARGET_RATIO}x")
    print(f"[INFO] Save directory: {SAVE_DIR}")
    print(f"[INFO] Info hash: {INFO_HASH}")
    print(f"[INFO] Max runtime: {MAX_RUNTIME}s ({MAX_RUNTIME/3600:.1f}h)")
    print("-" * 60)
    
    start_total = time.time()
    
    try:
        # Get torrent info
        ti = get_torrent_info()
        
        # Calculate remaining time
        elapsed = time.time() - start_total
        remaining_time = MAX_RUNTIME - elapsed
        
        # Check if we need to download
        expected_file = os.path.join(SAVE_DIR, ti.name())
        
        if os.path.exists(expected_file) and os.path.getsize(expected_file) == ti.total_size():
            print(f"[INFO] File already exists and is complete: {expected_file}")
            session, handle = seed_torrent(ti, SAVE_DIR, TARGET_RATIO, remaining_time)
        else:
            print("[INFO] File not found or incomplete, downloading...")
            session, handle = download_torrent(ti, SAVE_DIR, remaining_time)
            
            if running:
                # Check if download completed
                if handle.status().is_seeding:
                    elapsed = time.time() - start_total
                    remaining_time = MAX_RUNTIME - elapsed
                    print("[INFO] Starting seeding...")
                    session.remove_torrent(handle)
                    session, handle = seed_torrent(ti, SAVE_DIR, TARGET_RATIO, remaining_time)
                else:
                    print("[INFO] Download not complete, will continue in next run")
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cleanup()
    
    total_elapsed = time.time() - start_total
    print(f"[INFO] Total runtime: {time.strftime('%H:%M:%S', time.gmtime(total_elapsed))}")
    print("[INFO] Script completed!")
    return 0

if __name__ == '__main__':
    sys.exit(main())
