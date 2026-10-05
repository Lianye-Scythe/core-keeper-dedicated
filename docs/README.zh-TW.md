# Core Keeper 伺服器架設：Oracle Cloud A1 / ARM64 Docker 教學

<!-- 指令、預設值、安全提醒與文件範圍須和 ../README.md 在同一個 PR 同步更新。
     詳細技術文件暫時以英文維護。 -->

使用 Docker Compose 和 FEX，在 ARM64 Linux 主機上執行官方 Core Keeper
專用伺服器，讓朋友透過遊戲 ID 加入。主要驗證環境是 Oracle Cloud Ampere A1；
其他 ARM64 主機的相容性與效能仍需個別確認。

這是非官方社群專案，不提供遊戲用戶端。玩家仍需持有正版、版本相容的遊戲。
如果已有足夠的 x86-64 主機，可以考慮原生架服方案，不一定需要 FEX 轉譯。

[English README](../README.md) · [完整設定（英文）](configuration.md) ·
[更新與備份（英文）](maintenance.md) · [問題排查（英文）](troubleshooting.md)

## 專案提供哪些功能？

| 功能 | 提供內容 |
| --- | --- |
| 執行環境 | FEX / ARM64 Linux，主要在 Oracle Cloud Ampere A1 驗證 |
| 部署 | Docker Compose，持久保存存檔、遊戲檔案與快取目錄 |
| 遊戲安裝 | ARM64 原生 DepotDownloader，匿名下載 Steam 伺服器檔案 |
| 啟動更新 | 容器啟動時檢查並下載遊戲更新 |
| 定期維護 | 選用主機更新器：每小時檢查、自訂套用時段、備份與失敗回復 |
| 診斷 | 選用主機蒐證工具，限制紀錄保留數量與期限 |

此分支不建置 AMD64 或 Box64 映像；其他方案請參考[原專案](https://github.com/escapingnetwork/core-keeper-dedicated)。

> [!IMPORTANT]
> 從舊 Box64 部署移轉時，注意此分支的 `latest` 現在代表 FEX / ARM64。
> 替換既有容器前請先讀[移轉指南（英文）](migration.md)。

> [!NOTE]
> CI 檢查封裝與啟動流程，不能保證所有 ARM64 主機的長時間穩定性或效能。

## 開始前需要什麼？

- 已準備好的 ARM64 Linux 主機，以及 SSH 或終端機存取方式。
- 已安裝一般 rootful Docker，以及 Docker Compose 外掛 **2.24.0 以上**。
- 主機可以對外連線下載容器映像、Steam 遊戲伺服器檔案及連接 Steam。
- 足夠的記憶體與磁碟空間；映像之外，遊戲檔案、存檔和備份也會占用空間。

本教學假設主機及 Docker 已設定完成，不包含 Oracle 帳號申請或 VPS 建立流程。
不需要 privileged 容器，也不需要在主機註冊模擬器。

## 1. 取得專案並設定伺服器

```sh
git clone https://github.com/Lianye-Scythe/core-keeper-dedicated-fex.git
cd core-keeper-dedicated-fex/docker-compose-example
cp core.env.example core.env
chmod 600 core.env
id -u
id -g
```

編輯 `core.env`：

| 設定 | 怎麼填 |
| --- | --- |
| `PUID` / `PGID` | 範例各為 `1000`；分別填入上面兩個指令顯示的正整數 ID，使用預定管理資料的一般帳號 |
| `WORLD_NAME` | 自訂世界名稱，範例為 `Core Keeper Server` |
| `WORLD_INDEX` | 新伺服器先用 `0`；這是存檔槽位，不是遊戲版本 |
| `GAME_ID` | 留空，讓遊戲產生連線 ID |
| `MAX_PLAYERS` | 玩家上限，範例是 `8` |
| `ACTIVATE_ALL_CONTENT` | 範例是 `false`；舊世界啟用前先備份 |
| `UPDATE_GATE_ENABLED` | 範例是 `false`；主機更新器設定完成後才啟用 |

範例的 `PUID` / `PGID` 都是 `1000`，請依照自己的帳號修改。

其他設定先維持範例值。`core.env` 是私人設定檔，不要提交到 GitHub，
也不要公開包含密碼、API Key 或 Webhook 的內容。

## 2. 建立資料目錄並啟動

以下操作都在 `docker-compose-example` 目錄內進行。
若帳號沒有 Docker 操作權限，請在 Docker 指令前加上 `sudo`。

```sh
sudo mkdir -p /srv/corekeeper/{server-data,server-files,fex-cache,mesa-cache,update-control}
docker compose config --quiet
docker compose up -d
docker logs --tail 100 -f core-keeper-dedicated
```

第一次啟動會下載遊戲並建立世界，請預留數分鐘，不要一直重啟。
查看紀錄時按 `Ctrl+C` 只會停止追蹤紀錄，不會關閉伺服器。
容器會準備資料目錄的權限，遊戲則以非 root 帳號執行。

範例將資料放在 `/srv/corekeeper`。如果想使用另一顆硬碟，請先修改
Compose 的掛載來源路徑，依照[部署文件](deployment.md)設定，
不要在遊戲執行時直接搬動存檔。

## 3. 找到遊戲 ID，邀請朋友加入

```sh
docker exec core-keeper-dedicated cat /home/steam/core-keeper-dedicated/GameID.txt
```

等伺服器完成世界初始化後，在遊戲多人連線選單輸入這個 ID。
**ID 檔案已存在，不代表世界已經載入完成。**

預設使用遊戲 ID 連線，需要對外的 Steam 連線；此模式不需要發布遊戲連接埠。
若要用 IP 直接連線，請另外依照[直接連線設定](deployment.md#direct-connections)
處理連接埠及防火牆，不要套用遊戲 ID 模式的說明。

## 設定變更、更新與備份

修改 `core.env` 後，在同一個 Compose 目錄執行：

```sh
docker compose up -d
```

這會在設定變更時重新建立容器。只執行 `docker compose restart`
不會載入新的環境變數。
Compose `environment` 區段明確設定的值優先於 `core.env`。
世界種子、難度、Discord、快取等其他選項請看[完整設定（英文）](configuration.md)。

- **預設只在容器啟動時檢查遊戲更新。** 沒有自動安裝排程或存檔備份。
  只拉取新映像不會替換執行中的容器。
- 可選用[主機更新器](maintenance.md)：每小時檢查，在設定的時段套用更新，
  更新前備份並限制保留數量；沒有內容變更就不重啟。
  更新器會比較遊戲與映像內容，停止伺服器後備份，驗證新版本啟動，失敗時嘗試回復。
- 公開更新器範例使用 `04:00 UTC`，也就是台灣時間 `12:00`，保留兩份備份。
  請自行設定需要的時區與時段，不要假設它已設定成自己的遊玩習慣。
- 先安裝並設定主機更新器，再啟用 `UPDATE_GATE_ENABLED`。
- 更新備份包含所有存檔槽位及已安裝的遊戲檔案，但不是每日或異地備份。
  重要世界仍應另外備份。
- 主機更新器與診斷腳本需另行維護，不會隨容器映像更新自動替換。

> [!WARNING]
> `ACTIVATE_ALL_CONTENT` 預設關閉。對舊世界啟用額外內容可能永久改變存檔，
> 請先備份。不要讓兩個執行中的伺服器同時寫入相同存檔。

## Mod 與相容性

沿用原專案的 mod.io 模組安裝機制，預設關閉。需要自行提供 API 設定、
Mod 清單及依賴；並非所有 Mod 都已驗證在 FEX 下正常運作。
模組會在啟動時依清單重新下載，不受主機更新器的更新時段限制。
每次啟動會先清空受管理的 Mods 目錄，不要手動放檔案進去；
未指定版本的 Mod 可能在任何一次啟動時換成新版。
詳見[模組設定](configuration.md#discord-and-mods)。

本專案不是所有 ARM64 主機上的效能或長時間穩定性保證。
遇到問題請先看[排查文件](troubleshooting.md)，再到
[GitHub Issues](https://github.com/Lianye-Scythe/core-keeper-dedicated-fex/issues)
提供遊戲版本、主機環境及移除敏感資訊後的紀錄。

## 詳細文件（目前以英文維護）

| 文件 | 內容 |
| --- | --- |
| [部署](deployment.md) | 儲存路徑、權限、一般 Docker、直接連線與容器操作 |
| [設定](configuration.md) | 完整設定、預設值與優先順序 |
| [定期維護](maintenance.md) | 更新、備份保留、失敗回復與主機腳本升級 |
| [問題排查](troubleshooting.md) | 啟動失敗、連線問題與安全檢查 |
| [主機診斷](../ops/diagnostics/README.md) | 選用蒐證、紀錄保留與隱私 |
| [執行環境與建置政策](../fex/README.md) | FEX 設定、快取、Ubuntu 環境、映像標籤與依賴 |
| [移轉](migration.md) | 從 Box64 或舊映像／倉庫名稱移轉 |

## 來源與授權

本專案源自 [escapingnetwork/core-keeper-dedicated](https://github.com/escapingnetwork/core-keeper-dedicated)，
保留原作者貢獻、歷史與 MIT 授權，現在主要維護 FEX / ARM64 方案。
與 Pugstorm 或 FEX 官方無隸屬關係；遊戲及第三方元件各有自己的授權。
