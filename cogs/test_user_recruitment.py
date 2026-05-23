import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

# --- 設定 ---
TEST_USER_ROLE_ID = 1507709464998838422  # テストユーザーのロールID

class TestUserButtonView(View):
    def __init__(self):
        # timeout=None にすることで、Botが起動している限りボタンが有効になります
        super().__init__(timeout=None)

    @discord.ui.button(
        label="テストユーザーに参加する / 辞める", 
        style=discord.ButtonStyle.primary, 
        emoji="🧪", 
        custom_id="btn_toggle_test_user_role"  # このIDを固定するのが一番重要です！
    )
    async def toggle_role(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ このボタンはサーバー内でのみ有効です。", ephemeral=True)

        role = guild.get_role(TEST_USER_ROLE_ID)
        if not role:
            return await interaction.response.send_message("❌ 設定されたテストユーザーロールが見つかりません。", ephemeral=True)

        member = interaction.user
        if role in member.roles:
            try:
                await member.remove_roles(role)
                await interaction.response.send_message(f"🧪 {role.name} ロールを解除しました。テストへのご協力ありがとうございました！", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Botにロールを外す権限がありません（Botの役職順位が低いです）。", ephemeral=True)
        else:
            try:
                await member.add_roles(role)
                await interaction.response.send_message(f"🎉 {role.name} ロールを付与しました！今後テストのご案内が届きます。よろしくお願いします！", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Botにロールを付与する権限がありません（Botの役職順位が低いです）。", ephemeral=True)


class TestUserRecruitment(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="test_user_panel", description="【管理者専用】テストユーザー募集パネルを設置します")
    @commands.has_permissions(administrator=True)
    async def spawn_recruitment_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        emb = discord.Embed(
            title="🧪 ぎあBot テストユーザー大募集！",
            description=(
                "新機能の先行テストや、バグ修正の確認に協力してくれるメンバーを募集しています！\n\n"
                "**💡 参加するとどうなる？**\n"
                "• テストユーザー専用チャンネルが見えるようになります。\n"
                "• 新しいゲームなどの先行プレイやテストに参加できます！\n\n"
                "参加希望の方は、下のボタンを押してロールを受け取ってください。\n"
                "*(もう一度ボタンを押すと、いつでも辞めることができます)*"
            ),
            color=0x3498db
        )
        
        await interaction.channel.send(embed=emb, view=TestUserButtonView())
        await interaction.followup.send("✅ テストユーザー募集パネルをここに設置したよ！", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TestUserRecruitment(bot))