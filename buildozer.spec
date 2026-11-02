[app]
title = Slenderman Escape del Bosque
package.name = slendermanescape
package.domain = org.slenderescape
source.dir = .
source.include_exts = py,png,txt
version = 1.0
requirements = python3,pygame
orientation = all
fullscreen = 1
icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1
