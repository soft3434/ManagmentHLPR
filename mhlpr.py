
import os
import sys
import re
import ctypes
import shutil
import subprocess
import winreg
import difflib
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.align import Align
    from rich.prompt import Prompt
    from rich.text import Text
    from rich import box
except ImportError:
    print("Installing required components...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    os.execv(sys.executable, [sys.executable] + sys.argv)


APP = "MANAGMENTHLPR"
VERSION = "3.0"

console = Console()

REGISTRY_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
]


def administrator():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def restart_as_admin():
    if administrator():
        return True

    script = os.path.abspath(sys.argv[0])
    params = subprocess.list2cmdline([script] + sys.argv[1:])

    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        os.getcwd(),
        1
    )

    if result <= 32:
        console.print("[red]Administrator privileges were not granted.[/red]")
        input("Press ENTER...")
        return False

    sys.exit(0)


def setup_terminal():
    os.system("title MANAGMENTHLPR")
    os.system("mode con: cols=112 lines=40")

    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        user32 = ctypes.windll.user32

        width = 1120
        height = 820

        x = (user32.GetSystemMetrics(0) - width) // 2
        y = (user32.GetSystemMetrics(1) - height) // 2

        user32.MoveWindow(hwnd, x, y, width, height, True)
    except Exception:
        pass


def get_value(key, name, default=""):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def normalize(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def valid_directory(path):
    if not path:
        return None

    try:
        path = os.path.expandvars(str(path).strip().strip('"'))
        path = Path(path).resolve()

        if path.is_file():
            path = path.parent

        if path.is_dir():
            return path

    except (OSError, ValueError):
        pass

    return None


def icon_path(value):
    if not value:
        return None

    value = os.path.expandvars(str(value).strip())

    match = re.search(r'"([^"]+)"', value)

    if match:
        return valid_directory(match.group(1))

    match = re.search(r"(.+?\.exe)", value, re.I)

    if match:
        return valid_directory(match.group(1))

    return valid_directory(value)


def find_common_directory(name):
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
    ]

    target = normalize(name)
    candidates = []

    for root in roots:
        if not root:
            continue

        base = Path(root)

        if not base.exists():
            continue

        try:
            for item in base.iterdir():
                if not item.is_dir():
                    continue

                candidate = normalize(item.name)

                if candidate == target:
                    candidates.append(item.resolve())

                elif len(target) > 4 and (
                    candidate in target or target in candidate
                ):
                    candidates.append(item.resolve())

                if len(candidates) >= 5:
                    break

        except (PermissionError, OSError):
            continue

    return candidates


def detect_paths(key, app_name):
    results = []

    install_location = get_value(key, "InstallLocation")
    display_icon = get_value(key, "DisplayIcon")

    path = valid_directory(install_location)

    if path:
        results.append({
            "path": path,
            "source": "InstallLocation",
            "confidence": "HIGH"
        })

    path = icon_path(display_icon)

    if path and all(x["path"] != path for x in results):
        results.append({
            "path": path,
            "source": "DisplayIcon",
            "confidence": "HIGH"
        })

    for path in find_common_directory(app_name):
        if all(x["path"] != path for x in results):
            results.append({
                "path": path,
                "source": "Directory search",
                "confidence": "MEDIUM"
            })

    return results


def scan_applications():
    applications = []
    seen = set()

    for root, registry_path in REGISTRY_PATHS:
        try:
            main_key = winreg.OpenKey(root, registry_path)
        except OSError:
            continue

        try:
            count = winreg.QueryInfoKey(main_key)[0]

            for i in range(count):
                try:
                    sub_name = winreg.EnumKey(main_key, i)
                    key = winreg.OpenKey(main_key, sub_name)

                    name = get_value(key, "DisplayName")

                    if not name:
                        continue

                    if name.lower() in seen:
                        continue

                    if get_value(key, "SystemComponent", 0) == 1:
                        continue

                    if get_value(key, "ParentKeyName"):
                        continue

                    seen.add(name.lower())

                    applications.append({
                        "name": name,
                        "version": get_value(key, "DisplayVersion", "Unknown"),
                        "publisher": get_value(key, "Publisher", "Unknown"),
                        "uninstall": get_value(key, "UninstallString"),
                        "quiet": get_value(key, "QuietUninstallString"),
                        "paths": detect_paths(key, name)
                    })

                    winreg.CloseKey(key)

                except OSError:
                    continue

        finally:
            winreg.CloseKey(main_key)

    applications.sort(key=lambda x: x["name"].lower())

    return applications


def panel(title, content, subtitle="MANAGMENTHLPR"):
    console.clear()

    console.print()
    console.print(
        Align.center(
            Text("MANAGMENTHLPR", style="bold bright_cyan", justify="center")
        )
    )

    console.print(
        Align.center(
            Text(f"APPLICATION CONTROL SYSTEM  |  v{VERSION}",
                 style="dim")
        )
    )

    console.print()

    console.print(
        Align.center(
            Panel(
                content,
                title=f"[bold bright_cyan]{title}[/bold bright_cyan]",
                subtitle=f"[dim]{subtitle}[/dim]",
                border_style="bright_blue",
                box=box.ROUNDED,
                width=82,
                padding=(1, 3)
            )
        )
    )


def wait():
    console.input("\n[dim]Press ENTER to continue...[/dim]")


def message(title, text, status="cyan"):
    panel(
        title,
        Align.center(Text(text, style=status, justify="center"))
    )
    wait()


def show_application_table(applications):
    table = Table(
        box=box.ROUNDED,
        border_style="bright_blue",
        header_style="bold bright_cyan",
        expand=True
    )

    table.add_column("#", style="bright_blue", width=5)
    table.add_column("APPLICATION", style="white")
    table.add_column("VERSION", style="dim")
    table.add_column("PATH", style="green")

    for index, app in enumerate(applications, 1):
        location = (
            str(app["paths"][0]["path"])
            if app["paths"] else "Not detected"
        )

        table.add_row(
            str(index),
            app["name"],
            app["version"],
            location
        )

    return table


def application_list(applications):
    while True:
        panel(
            "INSTALLED APPLICATIONS",
            show_application_table(applications)
        )

        console.print(
            Align.center(
                f"[dim]Detected: {len(applications)} applications[/dim]"
            )
        )

        choice = Prompt.ask(
            "\n[bright_cyan]SELECT APPLICATION[/bright_cyan]",
            default="B"
        ).strip()

        if choice.lower() == "b":
            return

        if choice.lower() == "r":
            applications[:] = scan_applications()
            continue

        try:
            index = int(choice) - 1

            if 0 <= index < len(applications):
                application_menu(applications[index], applications)

        except ValueError:
            message("ERROR", "Invalid selection.", "red")


def application_information(app):
    table = Table(box=box.SIMPLE, show_header=False, expand=True)

    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Name", app["name"])
    table.add_row("Version", app["version"])
    table.add_row("Publisher", app["publisher"])
    table.add_row("Uninstaller", "Available" if app["uninstall"] else "Unavailable")

    for index, item in enumerate(app["paths"], 1):
        table.add_row(
            f"Path {index} ({item['confidence']})",
            str(item["path"])
        )
        table.add_row("Path source", item["source"])

    if not app["paths"]:
        table.add_row("Installation path", "Not detected")

    panel("APPLICATION INFORMATION", table)
    wait()


def open_folder(app):
    if not app["paths"]:
        message("OPEN DIRECTORY", "No installation directory detected.", "red")
        return

    if len(app["paths"]) == 1:
        path = app["paths"][0]["path"]
    else:
        options = "\n".join(
            f"{i}. {item['path']}"
            for i, item in enumerate(app["paths"], 1)
        )

        panel("SELECT DIRECTORY", options)

        try:
            index = int(Prompt.ask("Directory number")) - 1
            path = app["paths"][index]["path"]
        except (ValueError, IndexError):
            return

    os.startfile(str(path))


def move_application(app):
    if not app["paths"]:
        message("MOVE APPLICATION", "Installation directory not found.", "red")
        return

    if len(app["paths"]) > 1:
        panel(
            "SELECT SOURCE",
            "\n".join(
                f"{i}. {item['path']} [{item['confidence']}]"
                for i, item in enumerate(app["paths"], 1)
            )
        )

        try:
            index = int(Prompt.ask("Select path")) - 1
            source = app["paths"][index]["path"]
        except (ValueError, IndexError):
            return
    else:
        source = app["paths"][0]["path"]

    if not source.exists() or not source.is_dir():
        message("MOVE APPLICATION", "Directory does not exist.", "red")
        return

    if app["paths"][0]["confidence"] != "HIGH":
        message(
            "MOVE APPLICATION",
            "The installation path is not sufficiently verified. "
            "Moving is disabled for this path.",
            "yellow"
        )
        return

    panel(
        "MOVE APPLICATION",
        f"APPLICATION\n{app['name']}\n\n"
        f"SOURCE\n{source}\n\n"
        "Enter a destination parent directory."
    )

    destination_input = console.input(
        "\n[bright_cyan]DESTINATION > [/bright_cyan]"
    ).strip().strip('"')

    if not destination_input:
        return

    destination_parent = valid_directory(destination_input)

    if not destination_parent:
        message("MOVE ERROR", "Destination does not exist.", "red")
        return

    source = source.resolve()
    destination_parent = destination_parent.resolve()

    if destination_parent == source or source in destination_parent.parents:
        message("MOVE ERROR", "Invalid destination.", "red")
        return

    destination = destination_parent / source.name

    if destination.exists():
        message("MOVE ERROR", "Destination already exists.", "red")
        return

    panel(
        "CONFIRM MOVE",
        f"FROM\n{source}\n\nTO\n{destination}\n\n"
        "A directory junction will preserve the old application path.\n"
        "Some applications may still require reconfiguration."
    )

    if Prompt.ask("Type MOVE to confirm") != "MOVE":
        return

    try:
        shutil.move(str(source), str(destination))

        result = subprocess.run(
            [
                "cmd.exe", "/c", "mklink", "/J",
                str(source), str(destination)
            ],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            shutil.move(str(destination), str(source))

            message(
                "MOVE FAILED",
                "Could not create directory junction. "
                "Original directory was restored.",
                "red"
            )
            return

        app["paths"] = [
            {
                "path": destination,
                "source": "ManagmentHlpr",
                "confidence": "HIGH"
            }
        ]

        message(
            "MOVE COMPLETED",
            f"New location:\n{destination}",
            "green"
        )

    except Exception as error:
        message("MOVE ERROR", str(error), "red")


def uninstall_application(app):
    command = app["quiet"] or app["uninstall"]

    if not command:
        message("UNINSTALL", "Uninstaller not found.", "red")
        return

    panel(
        "UNINSTALL APPLICATION",
        f"APPLICATION\n{app['name']}\n\n"
        f"PUBLISHER\n{app['publisher']}\n\n"
        "The registered uninstaller will be started.\n"
        "Shared system files will not be manually deleted."
    )

    if Prompt.ask("Type DELETE to confirm") != "DELETE":
        return

    try:
        subprocess.Popen(command, shell=True)

        message(
            "UNINSTALLER STARTED",
            "Follow the uninstaller instructions.",
            "green"
        )

    except Exception as error:
        message("UNINSTALL ERROR", str(error), "red")


def application_menu(app, applications):
    while True:
        path = (
            str(app["paths"][0]["path"])
            if app["paths"] else "Not detected"
        )

        content = (
            f"[bold white]{app['name']}[/bold white]\n"
            f"[dim]{app['publisher']}[/dim]\n\n"
            f"[cyan]VERSION[/cyan]     {app['version']}\n"
            f"[cyan]LOCATION[/cyan]    {path}\n\n"
            "[bright_cyan]1[/bright_cyan]   Application information\n\n"
            "[bright_cyan]2[/bright_cyan]   Open installation directory\n\n"
            "[bright_cyan]3[/bright_cyan]   Move application\n\n"
            "[bright_cyan]4[/bright_cyan]   Uninstall application\n\n"
            "[bright_cyan]5[/bright_cyan]   Back"
        )

        panel("APPLICATION CONTROL", content)

        choice = Prompt.ask(
            "\n[bright_cyan]MANAGMENTHLPR[/bright_cyan]",
            default="5"
        )

        if choice == "1":
            application_information(app)

        elif choice == "2":
            open_folder(app)

        elif choice == "3":
            move_application(app)

        elif choice == "4":
            uninstall_application(app)
            applications[:] = scan_applications()
            return

        elif choice == "5":
            return


def main():
    setup_terminal()

    if not restart_as_admin():
        return

    applications = scan_applications()

    while True:
        content = (
            "\n"
            "[bold bright_cyan]APPLICATION MANAGEMENT[/bold bright_cyan]\n\n"
            "[bright_cyan]01[/bright_cyan]    Installed applications\n\n"
            "[bright_cyan]02[/bright_cyan]    Refresh database\n\n"
            "[bright_cyan]03[/bright_cyan]    System information\n\n"
            "[bright_cyan]04[/bright_cyan]    Exit\n\n"
            "────────────────────────────────────\n"
            f"[dim]Detected applications: {len(applications)}[/dim]\n"
            f"[dim]Administrator: {'YES' if administrator() else 'NO'}[/dim]"
        )

        panel("DASHBOARD", Align.center(content))

        choice = Prompt.ask(
            "\n[bright_cyan]MANAGMENTHLPR[/bright_cyan]",
            default="1"
        )

        if choice == "1":
            application_list(applications)

        elif choice == "2":
            panel("SCANNING", Align.center("[yellow]Scanning registry and directories...[/yellow]"))
            applications = scan_applications()

            message(
                "SCAN COMPLETED",
                f"Found {len(applications)} applications.",
                "green"
            )

        elif choice == "3":
            info = (
                f"OS: {sys.platform}\n"
                f"Python: {sys.version.split()[0]}\n"
                f"Architecture: {os.environ.get('PROCESSOR_ARCHITECTURE', 'Unknown')}\n"
                f"User: {os.environ.get('USERNAME', 'Unknown')}\n"
                f"Administrator: {administrator()}"
            )

            panel("SYSTEM INFORMATION", Align.center(info))
            wait()

        elif choice == "4":
            console.clear()
            console.print(
                Align.center("[bold bright_cyan]MANAGMENTHLPR CLOSED[/bold bright_cyan]")
            )
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.clear()
        sys.exit(0)
