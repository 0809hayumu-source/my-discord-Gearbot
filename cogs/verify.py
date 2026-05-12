import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio

# --- 設定 ---
AGREED_ROLE_ID = 1503334701446725632  # 「同意済み」のロールID
VERIFIED_ROLE_ID = 1495192303936208906 # 「認証済み」のロールID

# 【重要】管理者「ユーザーID」のリストに変更（ロールIDではなく）
ADMIN_USER_IDS = [719461059248783401, 718428067340615730] 

CATEGORY_ID = 1495289511461261353  # チケットを作成するカテゴリのID

# --- 管理者側の「承認」ボタン ---
class AdminApprovalView(ui.View):
    def __init__(self, user: discord.Member):
        super().__init__(timeout=None)
        self.user = user

    @ui.button(label="このユーザーを認証する", style=discord.ButtonStyle.success, emoji="👤", custom_id="approve_user")
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        # ユーザーIDを直接チェックするように修正
        if interaction.user.id not in ADMIN_USER_IDS:
            return await interaction.response.send_message("⚠️ この操作は許可された管理者のみ可能です。", ephemeral=True)

        role = interaction.guild.get_role(VERIFIED_ROLE_ID)
        if not role:
            return await interaction.response.send_message("❌ 認証済みロールが見つかりません。IDを確認してください。", ephemeral=True)

        try:
            # 認証済みロールを付与
            await self.user.add_roles(role)
            # 同意済みロールを外す（もし持っていれば）
            agreed = interaction.guild.get_role(AGREED_ROLE_ID)
            if agreed and agreed in self.user.roles:
                await self.user.remove_roles(agreed)

            await interaction.response.send_message(f"✅ {self.user.mention} さんの認証が完了しました！\nこのチャンネルは3秒後に削除されます。")
            
            await asyncio.sleep(3)
            await interaction.channel.delete()
        except discord.Forbidden:
            await interaction.response.send_message("❌ ボットの権限不足。ボットの役職を一番上に上げてください。")

# --- ユーザー側の「同意」ボタン ---
class VerifyView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="同意して申請する", style=discord.ButtonStyle.primary, emoji="📝", custom_id="agree_button")
    async def agree(self, interaction: discord.Interaction, button: ui.Button):
        guild = interaction.guild
        user = interaction.user
        
        agreed_role = guild.get_role(AGREED_ROLE_ID)
        if agreed_role:
            await user.add_roles(agreed_role)

        category = guild.get_channel(CATEGORY_ID)
        
        # 権限設定：@everyoneは見れない、ユーザー本人は見れる
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        
        # 管理者（個人）に閲覧権限を与える
        for admin_id in ADMIN_USER_IDS:
            admin_member = guild.get_member(admin_id)
            if admin_member:
                overwrites[admin_member] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        
        ticket_channel = await guild.create_text_channel(
            name=f"認証待機-{user.name}",
            category=category,
            overwrites=overwrites
        )

        emb = discord.Embed(
            title="🛡️ 認証リクエスト送信完了",
            description=(
                f"👤 **申請者:** {user.mention}\n"
                "----------------------------------\n"
                "✅ **ユーザーさんへ:**\n"
                "管理者が確認を行っています。このままお待ちください。\n\n"
                "🛠 **管理者へ:**\n"
                "内容を確認し、下のボタンで承認してください。"
            ),
            color=discord.Color.orange()
        )
        await ticket_channel.send(embed=emb, view=AdminApprovalView(user))
        
        await interaction.response.send_message(f"✅ 同意を受け付けました。{ticket_channel.mention} へ移動してください。", ephemeral=True)

class Verify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup_verify", description="承認制認証パネルを設置")
    @app_commands.default_permissions(administrator=True)
    async def setup_verify(self, interaction: discord.Interaction):
        emb = discord.Embed(
            title="🛡️ サーバー入会申請",
            description="ルールへの同意と管理者による認証が必要です。\n下のボタンで申請を開始してください。",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=emb, view=VerifyView())

async def setup(bot):
    await bot.add_cog(Verify(bot))