import os
import time
import base64
import asyncio
import aiohttp
import threading
import discord
from discord.ext import commands
from discord import Embed
from flask import Flask

# Web Server สำหรับ Render Health Check
app = Flask('')

@app.route('/')
def home():
    return "Bot is active!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# ตั้งค่า Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

GIF_URL = "https://cdn.discordapp.com/attachments/1488121649491480726/1553743455769993309/c0d7d11e29ec35f398c50ed6c59e227b.gif?ex=6aba5bdb&is=6ab90a5b&hm=7fd1f3fe05960b0ed45fced523584ad0bbc9e85335338c23443e136aad7f10d5&"
WHITE_COLOR = 0xFFFFFF

# ฟังก์ชันดึง/ยิง Discord API ด้วย User Token
async def api_req(method, endpoint, token, json_data=None):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    url = f"https://discord.com/api/v10{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, headers=headers, json=json_data) as resp:
            if resp.status in [200, 201, 204]:
                try:
                    return await resp.json(), resp.status
                except:
                    return None, resp.status
            return None, resp.status

# ระบบตรวจสอบ Token และ สิทธิ์การใช้งานแบบใหม่ (ไม่จำเป็นต้องเป็นหัวดิส)
async def check_permissions(token, src_id, dst_id, check_type):
    # 1. เช็คว่า User Token ถูกต้องไหม
    user, st = await api_req("GET", "/users/@me", token)
    if st != 200 or not user:
        return False, "<a:1000035604:1553747969176764486> UserToken ไม่ถูกต้องหรือหมดอายุอ้าาา"

    # 2. ดึงลิสเซิร์ฟเวอร์ทั้งหมดที่ Token นี้อยู่ผ่าน /users/@me/guilds (ไม่ติด 403 แม้ไม่ใช่หัวดิส)
    user_guilds, st_g = await api_req("GET", "/users/@me/guilds", token)
    if st_g != 200 or user_guilds is None:
        return False, "<a:1000035604:1553747969176764486> ไม่สามารถดึงข้อมูลดิสจาก UserToken ได้"

    src_guild = next((g for g in user_guilds if str(g['id']) == str(src_id)), None)
    dst_guild = next((g for g in user_guilds if str(g['id']) == str(dst_id)), None)

    # 3. เช็คว่าอยู่ในดิสต้นทางไหม
    if not src_guild:
        if check_type == 'emoji':
            return False, "<a:1000035604:1553747969176764486> UserTokenไม่อยู่ในดิสต้นทางอ้าาา"
        else:
            return False, "<a:1000035604:1553747969176764486> Tokenไม่อยู่ดิสต้นทาง"

    # 4. เช็คว่าอยู่ในดิสปลายทางไหม
    if not dst_guild:
        if check_type == 'emoji':
            return False, "<a:1000035604:1553747969176764486> UserTokenไม่อยู่ในดิสปรายทางอ้าาา"
        else:
            return False, "<a:1000035604:1553747969176764486> tokenไม่อยู่ดิสปรายทาง"

    # 5. เช็คสิทธิ์ในดิสปลายทางจาก Permission Bitfield ของ UserToken ทันที
    is_owner = dst_guild.get("owner", False)
    dst_perms = int(dst_guild.get("permissions", 0))

    # Bitwise Permission Flags:
    # ADMINISTRATOR = 0x8 (8)
    # MANAGE_ROLES = 0x10000000 (268435456)
    # MANAGE_EMOJIS_AND_STICKERS = 0x40000000 (1073741824)
    # MANAGE_CHANNELS = 0x10 (16)

    has_admin = (dst_perms & 0x8) == 0x8
    has_emoji_perm = (dst_perms & 0x40000000) == 0x40000000
    has_role_perm = (dst_perms & 0x10000000) == 0x10000000
    has_channel_perm = (dst_perms & 0x10) == 0x10

    has_perm = False
    if is_owner or has_admin:
        has_perm = True
    elif check_type == 'emoji':
        has_perm = has_emoji_perm
    elif check_type == 'role':
        has_perm = has_role_perm
    elif check_type == 'all':
        has_perm = has_role_perm or has_channel_perm or has_emoji_perm

    if not has_perm:
        if check_type == 'emoji':
            return False, "<a:1000035604:1553747969176764486> UserTokenไม่มีสิทธิ์จัดการอีโมจิอ้าา"
        else:
            return False, "<a:1000035604:1553747969176764486> Tokenไม่มีสิทธิ์จัดการบททางในดิสปรายทาง"

    return True, (src_guild, dst_guild)


# Modal หน้าต่างป๊อปอัพรับข้อมูล
class CopyModal(discord.ui.Modal):
    def __init__(self, copy_type: str):
        super().__init__(title="กรอกข้อมูลสำหรับคัดลอก")
        self.copy_type = copy_type

        self.token_input = discord.ui.TextInput(label="User Token", placeholder="วาง User Token ที่นี่...", required=True)
        self.src_input = discord.ui.TextInput(label="ID ดิสต้นทาง", placeholder="ไอดีดิสต้นทาง...", required=True)
        self.dst_input = discord.ui.TextInput(label="ID ดิสปลายทาง", placeholder="ไอดีดิสปลายทาง...", required=True)

        self.add_item(self.token_input)
        self.add_item(self.src_input)
        self.add_item(self.dst_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        token = self.token_input.value.strip()
        src_id = self.src_input.value.strip()
        dst_id = self.dst_input.value.strip()

        valid, result = await check_permissions(token, src_id, dst_id, self.copy_type)
        if not valid:
            embed = Embed(description=result, color=WHITE_COLOR)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        src_guild, dst_guild = result
        src_name = src_guild.get("name", "ต้นทาง")

        if self.copy_type == 'emoji':
            msg = "<a:1000035600:1553744803114647594> สำเร็จ ต้องการเริ่มก็อปเลยมั้ย <a:1000035601:1553746218528546836>"
        elif self.copy_type == 'role':
            msg = "<a:1000035600:1553744803114647594> สำเร็จ ต้องการเริ่มก็อปยศเลยมั้ย"
        else:
            msg = "<a:1000035600:1553744803114647594> สำเร็จ ต้องการเริ่มก็อปทั้งดิสเลยมั้ย"

        embed = Embed(description=msg, color=WHITE_COLOR)
        view = ConfirmActionView(token, src_id, dst_id, src_name, self.copy_type)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


# View ยืนยัน ปุ่ม 1.เริ่ม และ 2.ยกเลิก
class ConfirmActionView(discord.ui.View):
    def __init__(self, token, src_id, dst_id, src_name, copy_type):
        super().__init__(timeout=300)
        self.token = token
        self.src_id = src_id
        self.dst_id = dst_id
        self.src_name = src_name
        self.copy_type = copy_type

    @discord.ui.button(label="1. เริ่ม", style=discord.ButtonStyle.green)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        start_time = time.time()

        # ------------------ ก็อปแค่อีโมจิ ------------------
        if self.copy_type == 'emoji':
            emojis, _ = await api_req("GET", f"/guilds/{self.src_id}/emojis", self.token)
            emojis = emojis or []
            total = len(emojis)
            normal_cnt = sum(1 for e in emojis if not e.get('animated'))
            gif_cnt = sum(1 for e in emojis if e.get('animated'))

            copied = 0
            for e in emojis:
                ext = "gif" if e.get('animated') else "png"
                img_url = f"https://cdn.discordapp.com/emojis/{e['id']}.{ext}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(img_url) as r:
                        if r.status == 200:
                            b64 = base64.b64encode(await r.read()).decode('utf-8')
                            img_data = f"data:image/{ext};base64,{b64}"
                            await api_req("POST", f"/guilds/{self.dst_id}/emojis", self.token, {"name": e['name'], "image": img_data})
                copied += 1
                pct = int((copied / total) * 100) if total > 0 else 100

                prog_embed = Embed(
                    description=f"<a:1000035602:1553746826585178163> กำลังเริ่มก็อปอีโมจิจากดิส{self.src_name} "
                                f"อีโมจิมีทั้งหมด{total} อีโมจิปกติมีทั้งหมด{normal_cnt} "
                                f"อีโมจิแบบgif{gif_cnt} ตอนนี้เริ่มก็อปไปเเล้ว {pct}%",
                    color=WHITE_COLOR
                )
                await interaction.edit_original_response(embed=prog_embed, view=None)
                await asyncio.sleep(0.3)

            elapsed = int(time.time() - start_time)
            final_embed = Embed(
                description=f"<a:1000035603:1553747446322962512> สำเร็จ ก็อปอีโมจิทั้งหมดเสร็จเเล้ววว "
                            f"จำนวนemojiที่ก็อปมา{copied} ใช้เวลาไป {elapsed} วิ",
                color=WHITE_COLOR
            )
            await interaction.edit_original_response(embed=final_embed)

        # ------------------ ก็อปแค่อยศ ------------------
        elif self.copy_type == 'role':
            roles, _ = await api_req("GET", f"/guilds/{self.src_id}/roles", self.token)
            roles = [r for r in (roles or []) if r['name'] != '@everyone']
            total = len(roles)
            copied = 0

            for r in reversed(roles):
                payload = {
                    "name": r['name'],
                    "permissions": r['permissions'],
                    "color": r['color'],
                    "hoist": r['hoist'],
                    "mentionable": r['mentionable']
                }
                await api_req("POST", f"/guilds/{self.dst_id}/roles", self.token, payload)
                copied += 1
                pct = int((copied / total) * 100) if total > 0 else 100

                prog_embed = Embed(
                    description=f"<a:1000035603:1553747446322962512> สำเร็จ กำลังเริ่มก็อปยศ จากดิส{self.src_name} "
                                f"จำนวนยศทั้งหมด{total} เริ่มก็อปไปเเล้วประมาณ{pct}%",
                    color=WHITE_COLOR
                )
                await interaction.edit_original_response(embed=prog_embed, view=None)
                await asyncio.sleep(0.3)

            elapsed = int(time.time() - start_time)
            final_embed = Embed(
                description=f"<a:1000035605:1553751024710328450> สำเร็จจ มียศทั้งหมด {total} ใช้เวลาไป {elapsed} วิ",
                color=WHITE_COLOR
            )
            await interaction.edit_original_response(embed=final_embed)

        # ------------------ ก็อปทั้งดิส ------------------
        elif self.copy_type == 'all':
            prog_embed = Embed(
                description="<a:1000035600:1553744803114647594> สำเร็จ กำลังเริ่มก็อปทั้งดิส ตอนนี้เริ่มไปเเล้วทั้งหมด 5%",
                color=WHITE_COLOR
            )
            await interaction.edit_original_response(embed=prog_embed, view=None)

            # 1. ลบช่องเดิมในดิสปลายทาง
            channels, _ = await api_req("GET", f"/guilds/{self.dst_id}/channels", self.token)
            for c in channels or []:
                await api_req("DELETE", f"/channels/{c['id']}", self.token)
                await asyncio.sleep(0.2)

            # 2. เปลี่ยนชื่อดิสปลายทางให้เหมือนต้นทาง (ถ้ามีสิทธิ์)
            await api_req("PATCH", f"/guilds/{self.dst_id}", self.token, {"name": self.src_name})

            # 3. ก็อปยศ
            roles, _ = await api_req("GET", f"/guilds/{self.src_id}/roles", self.token)
            roles = [r for r in (roles or []) if r['name'] != '@everyone']
            for r in reversed(roles):
                await api_req("POST", f"/guilds/{self.dst_id}/roles", self.token, {
                    "name": r['name'], "permissions": r['permissions'], "color": r['color'],
                    "hoist": r['hoist'], "mentionable": r['mentionable']
                })
                await asyncio.sleep(0.2)

            # 4. ก็อปปี้หมวดหมู่และช่อง
            src_channels, _ = await api_req("GET", f"/guilds/{self.src_id}/channels", self.token)
            categories = [c for c in (src_channels or []) if c['type'] == 4]
            other_channels = [c for c in (src_channels or []) if c['type'] != 4]

            cat_map = {}
            for cat in categories:
                new_cat, _ = await api_req("POST", f"/guilds/{self.dst_id}/channels", self.token, {
                    "name": cat['name'], "type": 4
                })
                if new_cat:
                    cat_map[cat['id']] = new_cat['id']
                await asyncio.sleep(0.2)

            for ch in other_channels:
                payload = {
                    "name": ch['name'],
                    "type": ch['type'],
                    "topic": ch.get('topic'),
                    "bitrate": ch.get('bitrate'),
                    "user_limit": ch.get('user_limit'),
                    "rate_limit_per_user": ch.get('rate_limit_per_user'),
                    "parent_id": cat_map.get(ch.get('parent_id'))
                }
                await api_req("POST", f"/guilds/{self.dst_id}/channels", self.token, payload)
                await asyncio.sleep(0.2)

            # 5. ก็อปอีโมจิ
            emojis, _ = await api_req("GET", f"/guilds/{self.src_id}/emojis", self.token)
            for e in emojis or []:
                ext = "gif" if e.get('animated') else "png"
                img_url = f"https://cdn.discordapp.com/emojis/{e['id']}.{ext}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(img_url) as r:
                        if r.status == 200:
                            b64 = base64.b64encode(await r.read()).decode('utf-8')
                            img_data = f"data:image/{ext};base64,{b64}"
                            await api_req("POST", f"/guilds/{self.dst_id}/emojis", self.token, {"name": e['name'], "image": img_data})
                await asyncio.sleep(0.2)

            elapsed = int(time.time() - start_time)
            final_embed = Embed(
                description=f"<a:1000035606:1553754388030431323> สำเร็จจ ใช้เวลาไป {elapsed} วิ",
                color=WHITE_COLOR
            )
            await interaction.edit_original_response(embed=final_embed)

    @discord.ui.button(label="2. ยกเลิก", style=discord.ButtonStyle.red)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cancel_text = "<a:1000035597:1553744274447671327> ยกเลิกสำเร็จ" if self.copy_type == 'emoji' else "<a:1000035604:1553747969176764486> ยกเลิกสำเร็จ"
        embed = Embed(description=cancel_text, color=WHITE_COLOR)
        await interaction.response.edit_message(embed=embed, view=None)


# Dropdown ตัวเลือกคำสั่ง
class MainDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="ก็อปเเค่อีโมจิ",
                value="emoji",
                emoji="<a:1000035594:1553743074532917248>"
            ),
            discord.SelectOption(
                label="ก็อปเเค่ยศ",
                value="role",
                emoji="<a:1000035596:1553744104356188280>"
            ),
            discord.SelectOption(
                label="ก็อปหมด",
                value="all",
                emoji="<a:1000035597:1553744274447671327>"
            ),
            discord.SelectOption(
                label="ล้างตัวเลือก",
                value="clear",
                emoji="<a:1000035599:1553744566862090290>"
            )
        ]
        super().__init__(
            placeholder="กดลิสคำสั่ง",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="main_select_menu"
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "clear":
            embed = Embed(description="<a:1000035608:1553754881863458846> ล้างตัวเลือกสำเร็จ", color=WHITE_COLOR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_modal(CopyModal(selected))


class MainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MainDropdown())


@bot.event
async def on_ready():
    # ตั้งสถานะสตรีมหน้าโปรไฟล์บอท
    stream_activity = discord.Streaming(
        name="<a:1000035609:1553755387692453959> บอทจาก .gg//D1kd3eQ",
        url="https://www.twitch.tv/discord"
    )
    await bot.change_presence(activity=stream_activity)
    
    # ลงทะเบียน View Persistent ให้ทำงานตลอดเวลาแม้ออฟไลน์แล้วกลับมาออน
    bot.add_view(MainView())
    print(f"Logged in as {bot.user}")


@bot.command(name="gi")
async def gi_command(ctx: commands.Context):
    embed = Embed(
        title="<a:1000035591:1553742569685520384> ก็อปดิส-emoji",
        description=(
            "<a:1000035589:1553742398004269107> ใส่User Token \n\n"
            "<a:1000035593:1553742800875683920> เเล้วมึงก็เลือกเอาจะก็อปดิสหรืออีโมจิ ยศหรืออะไรเรื่องของมึง\n\n"
            "<a:1000035600:1553744803114647594> รับเเค่UserToken นะจ๊ะ อย่าลืม Tokenที่กรอกต้องมียศแอดมินเพื่อสร้างไรต่างๆ"
        ),
        color=WHITE_COLOR
    )
    embed.set_image(url=GIF_URL)
    
    await ctx.send(embed=embed, view=MainView())


# รัน Web Server แยก Thread และรัน Discord Bot
threading.Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "วาง_BOT_TOKEN_ตรงนี้")
    bot.run(TOKEN)
