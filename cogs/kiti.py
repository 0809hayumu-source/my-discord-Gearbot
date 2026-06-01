import discord
from discord import app_commands, ui
from discord.ext import commands

# --- 設定 ---
LOG_CHANNEL_ID = 1510919742825828362
ADMIN_IDS = {718428067340615730, 719461059248783401} # 2人の管理者をセットで定義

class CloseTicketView(ui.View):
    """スレッド内に設置する「閉じる」ボタンのView"""
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="この依頼を閉じる", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="dep_ticket_close")
    async def close(self, i: discord.Interaction, b: ui.Button):
        # 管理者チェック
        if i.user.id not in ADMIN_IDS:
            return await i.response.send_message("❌ この依頼を閉じる権限はありません。", ephemeral=True)
        
        await i.response.send_message("🔒 管理者によって依頼が完了（アーカイブ）されました。")
        if isinstance(i.channel, discord.Thread):
            await i.channel.edit(archived=True, locked=True)

class DeploymentModal(ui.Modal, title="基地代行の依頼内容"):
    detail = ui.TextInput(label="代行してほしい内容", style=discord.TextStyle.paragraph, placeholder="例: 〇〇してほしいです", required=True)

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        
        # 1. スレッド作成
        thread = await i.channel.create_thread(name=f"基地代行-{i.user.name}", type=discord.ChannelType.private_thread)
        await thread.add_user(i.user)
        
        # 2. 管理者を招待
        for aid in ADMIN_IDS:
            admin = i.guild.get_member(aid)
            if admin: await thread.add_user(admin)
        
        # 3. 案内と「閉じる」ボタンを送信
        admin_mentions = " ".join([f"<@{aid}>" for aid in ADMIN_IDS])
        msg = await thread.send(
            content=f"{i.user.mention} 様の依頼を受け付けました。\n{admin_mentions} 様、ご確認お願いします。\n\n**依頼内容:** {self.detail.value}",
            view=CloseTicketView()
        )
        await msg.pin()
        
        # 4. ログ送信
        log_chan = i.client.get_channel(LOG_CHANNEL_ID)
        if log_chan:
            emb = discord.Embed(title="🚀 基地代行依頼", color=0xf1c40f)
            emb.add_field(name="依頼者", value=i.user.mention, inline=False)
            emb.add_field(name="内容", value=self.detail.value, inline=False)
            await log_chan.send(embed=emb)
        
        await i.followup.send(f"✅ スレッドを作成しました: {thread.mention}", ephemeral=True)

class DeploymentPanelView(ui.View):
    def __init__(self): super().__init__(timeout=None)
    @ui.button(label="🚀 基地代行を依頼する", style=discord.ButtonStyle.success, custom_id="dep_ticket_open")
    async def open(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(DeploymentModal())

class BaseDeploymentTicket(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot
        # 永続化ビューの登録
        self.bot.add_view(DeploymentPanelView())
        self.bot.add_view(CloseTicketView())

    @app_commands.command(name="setup_dep_panel", description="【管理者専用】基地代行受付パネルを設置")
    @commands.has_permissions(administrator=True)
    async def setup(self, i: discord.Interaction):
        emb = discord.Embed(title="🚀 基地代行受付窓口", description="ボタンを押して依頼内容を送信してください。", color=0xf1c40f)
        await i.channel.send(embed=emb, view=DeploymentPanelView())
        await i.response.send_message("✅ パネル設置完了", ephemeral=True)

async def setup(bot): await bot.add_cog(BaseDeploymentTicket(bot))