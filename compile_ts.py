import os
import subprocess
import glob
import sys

def main():
    if not os.path.exists('i18n'):
        print("i18n directory not found")
        return

    ts_files = glob.glob('i18n/*.ts')
    if not ts_files:
        print("No .ts files found in i18n directory")
        return

    for ts_file in ts_files:
        qm_file = ts_file.replace('.ts', '.qm')
        print(f"Compiling {ts_file} -> {qm_file}")
        
        # Try to find lrelease
        lrelease_path = 'lrelease'
        
        # Check if lrelease is in PATH
        from shutil import which
        if which('lrelease'):
            lrelease_path = 'lrelease'
        else:
            # Search in common locations
            search_paths = [
                os.path.join(os.path.dirname(sys.executable), 'Scripts'),
                os.path.join(os.path.dirname(sys.executable), 'Lib', 'site-packages', 'qt6_applications', 'Qt', 'bin'),
                os.path.join(os.path.dirname(sys.executable), 'Lib', 'site-packages', 'PyQt6', 'Qt6', 'bin'),
            ]
            
            for path in search_paths:
                exe = os.path.join(path, 'lrelease.exe')
                if os.path.exists(exe):
                    lrelease_path = exe
                    break
        
        print(f"Using lrelease: {lrelease_path}")
        
        cmd = [lrelease_path, ts_file, '-qm', qm_file]
        try:
            subprocess.run(cmd, check=True)
            print(f"Success: {qm_file}")
        except FileNotFoundError:
            print(f"Error: '{lrelease_path}' command not found.")
            print("Please install via: pip install qt6-tools")
            print("Or add it to your PATH manually.")
        except subprocess.CalledProcessError as e:
            print(f"Error during compilation: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()
