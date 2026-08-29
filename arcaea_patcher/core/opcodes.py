# AArch64 opcodes.
ARM64_RET = b"\xC0\x03\x5F\xD6"                       # RET
ARM64_RET_1 = b"\x20\x00\x80\x52" + ARM64_RET         # MOV W0, #1; RET
ARM64_RET_0 = b"\x00\x00\x80\x52" + ARM64_RET         # MOV W0, #0; RET

# ARM32 ARM-mode opcodes.
ARM32_RET = b"\x1E\xFF\x2F\xE1"                       # BX LR
ARM32_RET_1 = b"\x01\x00\xA0\xE3" + ARM32_RET         # MOV R0, #1; BX LR
ARM32_RET_0 = b"\x00\x00\xA0\xE3" + ARM32_RET         # MOV R0, #0; BX LR

# Thumb opcodes.
THUMB_RET = b"\x70\x47"                               # BX LR
THUMB_RET_1 = b"\x01\x20\x70\x47"                     # MOV R0, #1; BX LR
THUMB_RET_0 = b"\x00\x20\x70\x47"                     # MOV R0, #0; BX LR