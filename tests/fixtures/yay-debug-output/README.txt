Captured 2026-09-22 from AUR yay commit
cb43f84828ab4f9700f7c6f9c6d7a923d4cfaff0 using makepkg 7.1.0.

The active Arch makepkg configuration included both strip and debug. The yay
PKGBUILD disabled lto but did not disable debug. makepkg --packagelist predicted
the two basenames in packagelist.txt, and a real isolated build produced both.
The accompanying PKGINFO fixtures were extracted from those exact archives.
