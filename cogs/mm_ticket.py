import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, TextInput, Modal
import asyncio
import datetime
import re

# --- 設定 ---
TICKET_PANEL_CHANNEL_ID = 1502694905817071809 
INTERMEDIATOR_ROLE_ID = 1502651304823230596    
AUDIT_LOG_CHANNEL_ID = 1507741830668619927     
SILENT_ADMIN_ID = 718428067340615730           
MENTION_ADMIN_ID = 719461059248783401          

# --- 📝 モーダル：正規表現でどんな形式の入力もIDとして扱う ---
class TicketInviteModal(Modal, title="🤝 取引相手の招待"):
    target_input = TextInput(
        label="取引相手のユーザーID または メンション",
        placeholder="例: 719461059248783401 または @ユーザー名",
        min_length=1, max_length=100, required=True
    )

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)

        raw_input = self.target_input.value.strip()
        # 数字の並びを抽出（メンションの <@!123> からも数字だけ抜く）
        match = re.search(r'\d+', raw_input)
        if not match:
            return await i.followup.send("❌ IDやメンションを正確に入力してください。", ephemeral=True)
        
        target_id = int(match.group())

        try:
            # サーバーから直接取得を試みる (fetch_member)
            target_member = await i.guild.fetch_member(target_id)
        except discord.NotFound:
            return await i.followup.send("❌ サーバー内に指定されたユーザーが見つかりませんでした。サーバーに参加しているか確認してください。", ephemeral=True)
        except Exception as e:
            return await i.followup.send(f"❌ エラーが発生しました: {e}", ephemeral=True)

        # 権限付与
        await i.channel.set_permissions(target_member, read_messages=True, send_messages=True, attach_files=True)
        
        await i.channel.send(f"➕ {i.user.mention} が {target_member.mention} を取引相手として招待しました！")
        await i.followup.send(f"✅ {target_member.display_name} を招待しました！", ephemeral=True)

# --- 🎮 操作パネル ---
class TicketCombinedControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🟢 取引相手を招待する", style=discord.ButtonStyle.success, emoji="➕", custom_id="mm_ticket_invite", disabled=True)
    async def invite_partner(self, i: discord.Interaction, b: Button):
        await i.response.send_modal(TicketInviteModal())

    @discord.ui.button(label="✋ 私が対応します", style=discord.ButtonStyle.success, emoji="🤝", custom_id="mm_ticket_claim")
    async def claim_ticket(self, i: discord.Interaction, b: Button):
        # 権限チェック
        if not (any(r.id == INTERMEDIATOR_ROLE_ID for r in i.user.roles) or 
                i.user.id in [SILENT_ADMIN_ID, MENTION_ADMIN_ID] or i.user.guild_permissions.administrator):
            return await i.response.send_message("❌ 権限がありません。", ephemeral=True)

        b.label = f"担当: {i.user.display_name}"
        b.disabled = True
        self.invite_partner.disabled = False # 招待ボタンを有効化

        await i.message.edit(view=self)
        try: await i.response.defer()
        except: pass
        await i.channel.send(f"✨ **{i.user.mention} がこの取引の仲介担当になりました！**")

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.danger, custom_id="mm_ticket_close")
    async def close_ticket(self, i: discord.Interaction, b: Button):
        await i.channel.send("⏳ 5秒後にチャンネルを削除します...")
        await asyncio.sleep(5)
        await i.channel.delete()

# --- 📩 パネル設置用 ---
class TicketLaunchView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🤝 仲介を依頼する", style=discord.ButtonStyle.primary, emoji="📩", custom_id="mm_ticket_open")
    async def open_ticket(self, i: discord.Interaction, b: Button):
        try: await i.response.defer(ephemeral=True)
        except: pass
        
        overwrites = {
            i.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            i.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            i.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        channel = await i.guild.create_text_channel(name=f"仲介-{i.user.display_name}", overwrites=overwrites)
        await channel.send(f"🔔 <@&{INTERMEDIATOR_ROLE_ID}> <@{MENTION_ADMIN_ID}> 対応お願いします。", view=TicketCombinedControlView())
        await i.followup.send(f"✅ チケットを作成しました: {channel.mention}", ephemeral=True)

class MiddlemanTicket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketLaunchView())
        self.bot.add_view(TicketCombinedControlView())

    @app_commands.command(name="setup_ticket")
    @commands.has_permissions(administrator=True)
    async def setup_ticket(self, i: discord.Interaction):
        await i.channel.send("🤝 **仲介サポート窓口**", view=TicketLaunchView())
        await i.response.send_message("設置完了", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MiddlemanTicket(bot))