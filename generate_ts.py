import os
import subprocess
import sys

def main():
    # Ensure i18n directory exists
    if not os.path.exists('i18n'):
        os.makedirs('i18n')

    # Source files to scan
    files = [
        'ui/main_window.py',
        'ui/dialogs/settings_dialog.py',
        'ui/dialogs/prompt_editor.py',
        'ui/dialogs/about_dialog.py',
        'ui/dialogs/report_dialog.py',
        'ui/components/video_player.py',
        'ui/components/delegates.py',
        'ui/sections/subtitle_table.py',
        'ui/sections/lqa_details_panel.py',
        'ui/sections/log_panel.py',
    ]
    
    # Verify files exist
    valid_files = []
    for f in files:
        if os.path.exists(f):
            valid_files.append(f)
        else:
            print(f"Warning: File {f} not found, skipping.")
            
    if not valid_files:
        print("No source files found!")
        return

    # Output file
    ts_file = 'i18n/kaoche_en.ts'
    
    # Command
    cmd = ['pylupdate6'] + valid_files + ['-ts', ts_file]
    
    print(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print(f"Successfully generated {ts_file}")
        
        # Post-process to replace backslashes with forward slashes
        try:
            with open(ts_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content.replace('filename="..\\', 'filename="../')
            
            if new_content != content:
                with open(ts_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print("Normalized paths to use forward slashes.")
                
        except Exception as e:
            print(f"Warning: Failed to post-process .ts file: {e}")

        print("Now use Qt Linguist to translate the strings, then run 'lrelease' to generate .qm files.")
    except Exception as e:
        print(f"Error running pylupdate6: {e}")
        # Try finding pylupdate6 via python module
        print("Trying python -m PyQt6.lupdate...")
        # Note: PyQt6 usually provides utils differently.
        # But let's assume pylupdate6 is in path as verified.

if __name__ == "__main__":
    main()
