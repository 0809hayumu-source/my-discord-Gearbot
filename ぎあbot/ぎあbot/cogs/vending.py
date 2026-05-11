import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button

# --- 管理者承認View ---
class AdminVendingVerifyView(View):
    def __init__(self, bot, item_name, user):
        super().__init__(timeout=None)
        self.bot, self.item_name, self.user = bot, item_name, user

    @discord.ui.button(label="【管理者用】支払いを承認する", style=discord.ButtonStyle.danger)
    async def verify(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 権限がありません。", ephemeral=True)
        
        # 承認後の表示更新
        await interaction.response.edit_message(content=f"✅ **{self.item_name}** の購入を承認しました！", view=None)
        try:
            # ユーザーへの通知も「商品購入」に変更
            await self.user.send(f"🛍️ 「**{self.item_name}**」の入金確認が完了し、承認されました！ありがとうございます！")
        except:
            pass

# --- 自販機購入モーダル ---
class VendingPurchaseModal(Modal):
    def __init__(self, bot):
        # タイトルを「商品購入申請」に変更
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
        
        # カテゴリIDだった場合の自動回避ロジック
        if isinstance(target, discord.CategoryChannel):
            if target.text_channels:
                target = target.text_channels[0]
        
        if not target or not hasattr(target, 'send'):
            return await interaction.followup.send("❌ 送信先チャンネルが見つかりませんでした。", ephemeral=True)
        
        # 管理者向けEmbedのデザイン
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

# --- 自販機Cog ---
class Vending(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="vending", description="自販機メニューを表示します")
    async def vending_menu(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        try:
            # ユーザー向けメッセージ
            embed = discord.Embed(
                title="🥤 ぎあBot 自販機", 
                description="下のボタンから商品の購入申請ができます。", 
                color=0x3498db
            )
            
            view = View(timeout=None)
            # ボタンも「購入する」で統一
            buy_btn = Button(label="🛒 購入する", style=discord.ButtonStyle.success)
            
            async def buy_callback(i: discord.Interaction):
                await i.response.send_modal(VendingPurchaseModal(self.bot))
                
            buy_btn.callback = buy_callback
            view.add_item(buy_btn)

            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            print(f"Error in vending: {e}")
            await interaction.followup.send("❌ メニュー表示に失敗しました。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Vending(bot))