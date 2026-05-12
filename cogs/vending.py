import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button

# --- 管理者承認View ---
class AdminVendingVerifyView(View):
    # main.pyから呼び出せるよう引数をオプション(None)に設定
    def __init__(self, bot=None, item_name=None, user=None):
        super().__init__(timeout=None) # 永続化
        self.bot, self.item_name, self.user = bot, item_name, user

    @discord.ui.button(
        label="【管理者用】支払いを承認する", 
        style=discord.ButtonStyle.danger,
        custom_id="admin_vending_verify_permanent" # IDを固定
    )
    async def verify(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 権限がありません。", ephemeral=True)
        
        await interaction.response.edit_message(content=f"✅ **{self.item_name}** の購入を承認しました！", view=None)
        try:
            await self.user.send(f"🛍️ 「**{self.item_name}**」の入金確認が完了し、承認されました！ありがとうございます！")
        except:
            pass

# --- 自販機購入モーダル (変更なし) ---
class VendingPurchaseModal(Modal):
    def __init__(self, bot):
        super().__init__(title="商品購入申請")
        self.bot = bot
        
        self.item_name = TextInput(
            label='購入する商品名', 
            placeholder="例：ガチャチケット、限定ロールなど", 
            required=True
        )
        self.link = TextInput(
            label='PayPayリンク', 
            placeholder="https://paypay.me/...", 
            required=True
        )
        
        self.add_item(self.item_name)
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        target_id = 1496365899610066974
        target = self.bot.get_channel(target_id)
        
        if isinstance(target, discord.CategoryChannel):
            if target.text_channels:
                target = target.text_channels[0]
        
        if not target or not hasattr(target, 'send'):
            return await interaction.followup.send("❌ 送信先チャンネルが見つかりませんでした。", ephemeral=True)
        
        embed = discord.Embed(title="⌛ 商品購入の支払い確認待ち", color=0xF1C40F)
        embed.add_field(name="📦 商品名", value=f"**{self.item_name.value}**", inline=False)
        embed.add_field(name="👤 申請者", value=interaction.user.mention, inline=True)
        embed.add_field(name="🔗 送金リンク", value=self.link.value, inline=False)
        
        admin_content = f"【管理者用】送金を確認したら承認ボタンを押してください。\n{self.link.value}"
        
        await target.send(
            content=admin_content,
            embed=embed, 
            view=AdminVendingVerifyView(self.bot, self.item_name.value, interaction.user)
        )
        
        await interaction.followup.send(f"✅ 「{self.item_name.value}」の購入申請を送信しました。", ephemeral=True)

# --- ユーザー用ボタンView ---
class VendingView(View):
    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="🛒 購入する", 
        style=discord.ButtonStyle.success,
        custom_id="vending_buy_btn_permanent" # IDを固定
    )
    async def buy_callback(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(VendingPurchaseModal(self.bot))

# --- 自販機Cog ---
class Vending(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="vending", description="自販機メニューを表示します")
    async def vending_menu(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        try:
            embed = discord.Embed(
                title="🥤 ぎあBot 自販機", 
                description="下のボタンから商品の購入申請ができます。", 
                color=0x3498db
            )
            # 独立させたVendingViewを使用して送信
            await interaction.followup.send(embed=embed, view=VendingView(self.bot))
        except Exception as e:
            print(f"Error in vending: {e}")
            await interaction.followup.send("❌ メニュー表示に失敗しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Vending(bot))