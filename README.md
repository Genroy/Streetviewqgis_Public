# Streetviewqgis_Public
Plugin that allows users to open Google Street View in a dock widget inside QGIS.
# StreetView QGIS Plugin
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](https://plugins.qgis.org/plugins/)
[![Downloads](https://img.shields.io/badge/downloads-100%2B-blue)](https://plugins.qgis.org/plugins/)
[![License](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
---
## 🇬🇧 English
A QGIS plugin that allows you to view Google Street View interactively by clicking on the map canvas.
Developed with ❤️ by **Thamoon Kedkaew CeJ** 
### Features

- Open a dockable window inside QGIS  
- Click anywhere on the map to open the corresponding Google Street View  
- Support coordinates to WGS84 (EPSG:4326)  
- Lightweight, simple, and fast
---
### Requirements
- QGIS 3.4  or move
- Python 3.x  ormove
- Qt WebEngine (included in QGIS)  
- A valid Google Maps API key
---
### Installation
1️Download the plugin ZIP file  
2️Open QGIS → `Plugins` → `Manage and Install Plugins` → `Install from ZIP`  
3️Select the downloaded ZIP file and install
---
### Setup
Before using the plugin, **you must provide your own Google Maps API key**.
To do this:
- Open the plugin code (`streetview_dock.py`)
- Replace the placeholder API key (`YOUR_API_KEY_HERE`) with your actual key
---
### How to Use
- Activate the plugin from the QGIS Plugins menu  
- Click the **Street View** toolbar button  
- A dock window will open on the right side  
- Click anywhere on the map — the Google Street View will appear instantly!
---
### License
MIT License
---
### Credits

Developed by:
- **Thamoon Kedkaew Cejay** (Original Developer)
- E-Mail Pongsakornche@gmail.com
- Special thanks to the QGIS community!
---

## 🇹🇭 ภาษาไทย
ปลั๊กอิน QGIS ที่ช่วยให้คุณดู **Google Street View** แบบโต้ตอบได้ โดยการคลิกบนแผนที่แบบวิตเจ็ต
พัฒนาโดย ❤️ **Thamoon Kedkaew Cej** 
### คุณสมบัติ
เปิดหน้าต่างฝังใน QGIS  
คลิกที่ใดก็ได้บนแผนที่เพื่อดู Google Street View ของจุดนั้น  
โปรดตั้งค่าพิกัด CRS เป็น WGS84 (EPSG:4326)  
---
### ความต้องการระบบ
- QGIS 3.4  
- Python 3.x  
- Qt WebEngine (รวมมาใน QGIS)  
- Google Maps API key ที่ใช้งานได้
- QtWebEngine
---
### การติดตั้ง
1️ดาวน์โหลดไฟล์ ZIP ของปลั๊กอิน  
2️เปิด QGIS → `ปลั๊กอิน` → `จัดการและติดตั้งปลั๊กอิน` → `ติดตั้งจาก ZIP`  
3️เลือกไฟล์ ZIP ที่ดาวน์โหลดมาและติดตั้ง
---
### การตั้งค่า
ก่อนใช้งาน **คุณต้องใส่ Google Maps API key ของคุณเอง**
วิธีทำ:
- เปิดไฟล์โค้ด (`streetview_dock.py`)  
- แทนที่ API key ตัวอย่าง (`YOUR_API_KEY_HERE`) ด้วย key จริงของคุณ
---
### วิธีการใช้
- เปิดใช้งานปลั๊กอินจากเมนูปลั๊กอิน  
- คลิกปุ่ม **Street View** ที่แถบเครื่องมือ  
- จะมีหน้าต่างด้านข้างปรากฏขึ้น  
- คลิกที่ใดก็ได้บนแผนที่ — Google Street View จะปรากฏทันที!
---
### ใบอนุญาต

---
### เครดิต
พัฒนาโดย:
- **Thamoon kedkaew CeJ** (นักพัฒนาดั้งเดิม)
ขอขอบคุณชุมชน QGIS สำหรับแรงบันดาลใจและการสนับสนุน!
---
### Repository 
- GitHub Repository: [https://github.com/Genroy/Streetviewqgis_Public
- E-Mail Pongsakornche@gmail.com
(C) 2011-2025 GeoApt LLC - geoapt.com
