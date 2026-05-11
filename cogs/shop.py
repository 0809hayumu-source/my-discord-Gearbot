import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button

# --- [設定] 招待コードと割引率 ---
INVITE_CODES = {
    "WELCOME30": 0.7,
    "WELCOME50": 0.7,
    "GEA30": 0.7
}

# --- 1. 管理者が承認ボタンを押した時の処理 ---
class AdminCoinVerifyView(View):
    def __init__(self, bot, coins, user, price, link, code_used):
        super().__init__(timeout=None)
        self.bot, self.coins, self.user, self.price, self.link = bot, coins, user, price, link
        self.code_used = code_used

    @discord.ui.button(label="【管理者用】支払いを承認する", style=discord.ButtonStyle.danger)
    async def verify(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 権限がありません", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        self.bot.add_data(self.user.id, coins=self.coins)
        
        await interaction.edit_original_response(content=f"✅ {self.user.display_name}さんに {self.coins}枚 付与しました！", view=None)
        
        try:
            await self.user.send(f"🪙 コインショップでの購入が承認されました！\n付与枚数: {self.coins}枚")
        except:
            pass

# --- 2. 購入時の入力フォーム ---
class CoinPaymentModal(Modal):
    def __init__(self, bot, price, coins):
        super().__init__(title=f"{price}円コイン購入申請")
        self.bot, self.price, self.coins = bot, price, coins
        
        self.info = TextInput(label='PayPayリンク', placeholder='https://paypay.me/...', required=True)
        self.invite_code = TextInput(label='招待コード', placeholder='持っていない場合は空欄でOK', required=False)
        
        self.add_item(self.info)
        self.add_item(self.invite_code)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        final_price = self.price
        code_status = "未使用"
        
        # 招待コードの判定
        input_code = self.invite_code.value.strip()
        if input_code in INVITE_CODES:
            discount = INVITE_CODES[input_code]
            final_price = int(self.price * discount)
            code_status = f"✅ 適用済み ({input_code})"
        elif input_code != "":
            code_status = f"❌ 無効なコード ({input_code})"

        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="支払管理ログ・ガチャログ")
        channel = await guild.create_text_channel(name=f"購入-{interaction.user.name}", category=category)
        
        embed = discord.Embed(title="⌛ 支払い確認待ち (コイン)", color=0xE67E22)
        embed.add_field(name="購入者", value=interaction.user.mention, inline=True)
        embed.add_field(name="支払い金額", value=f"**{final_price}円**", inline=True)
        embed.add_field(name="付与枚数", value=f"{self.coins}枚", inline=True)
        embed.add_field(name="元の金額 / コード", value=f"{self.price}円 / {code_status}", inline=False)
        embed.add_field(name="PayPayリンク", value=self.info.value, inline=False)
        
        await channel.send(
            embed=embed, 
            view=AdminCoinVerifyView(self.bot, self.coins, interaction.user, final_price, self.info.value, input_code)
        )
        
        await interaction.followup.send(
            f"✅ 申請しました。割引価格: **{final_price}円**\n専用チャンネル {channel.mention} でお待ちください。", 
            ephemeral=True
        )

# --- 3. ショップコマンド ---
class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="shop", description="コイン購入メニューを表示")
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        
        prices = [(500, 500), (1000, 1050), (3000, 3200), (5000, 5500), (10000, 11500)]
        embed = discord.Embed(title="🪙 コインショップ", description="招待コードで**30%OFF**になります！", color=discord.Color.gold())
        
        view = View(timeout=None)
        for p, c in prices:
            btn = Button(label=f"{p}円 ({c}枚)", style=discord.ButtonStyle.primary)
            def make_callback(pv, cv):
                async def callback(i): await i.response.send_modal(CoinPaymentModal(self.bot, pv, cv))
                return callback
            btn.callback = make_callback(p, c)
            view.add_item(btn)
            
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Shop(bot))