import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import asyncio
import datetime

# --- [設定] 通知を送りたい特定の個人メンション ---
ADMIN_USER_MENTIONS = "<@719461059248783401> <@718428067340615730>"
ALLOWED_ROLE_ID = 1499355000185557108 # コイン付与可ロール

# --- 1. 買取申請用モーダル ---
class RobloxTradeModal(Modal):
    def __init__(self, bot):
        super().__init__(title="ロブロックス買取申請フォーム")
        self.bot = bot
        self.roblox_name = TextInput(label='ロブロックス名', placeholder="例: Roblox_User123", required=True)
        self.char_name = TextInput(label='送るキャラの名前', placeholder="例: ゴジラ", required=True)
        self.mutation = TextInput(label='変異', placeholder="例: なし、金変異など", required=True)
        self.hope_price = TextInput(label='希望金額 (コイン)', placeholder="例: 5000", required=True)
        
        self.add_item(self.roblox_name)
        self.add_item(self.char_name)
        self.add_item(self.mutation)
        self.add_item(self.hope_price)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📝 買取申請内容", color=0x3498DB)
        embed.add_field(name="ロブロ名", value=self.roblox_name.value, inline=True)
        embed.add_field(name="キャラ名", value=self.char_name.value, inline=True)
        embed.add_field(name="変異", value=self.mutation.value, inline=True)
        embed.add_field(name="希望額", value=f"{self.hope_price.value} コイン", inline=False)
        embed.set_footer(text="この後に「証拠写真」をこのチャンネルにアップロードしてください。")

        # 💡 再起動してもデータを見失わないように custom_id へ「申請者ID」と「金額」を埋め込む
        view = RobloxAdminVerifyView(self.bot, interaction.user.id, self.hope_price.value)
        
        content = (
            "✅ 入力が完了しました！\n"
            "```diff\n"
            "- 【重要】この後に必ず「証拠となる写真」をここにアップロードしてください！\n"
            "```\n"
            f"（写真を送ると {ADMIN_USER_MENTIONS} に通知がいきます）"
        )
        await interaction.response.send_message(content=content, embed=embed, view=view)


# --- 2. 管理者承認ボタン（永続化対応版） ---
class RobloxAdminVerifyView(View):
    def __init__(self, bot, applicant_id: int, amount: str):
        super().__init__(timeout=None)
        self.bot = bot
        self.applicant_id = applicant_id
        self.amount = str(amount).replace(",", "")
        
        self.clear_items()
        # 💡 custom_id に申請者と金額の情報を合体させて埋め込む
        self.add_item(Button(
            label="上記「買取希望額」で承認（在庫から付与）", 
            style=discord.ButtonStyle.success,
            custom_id=f"rt_approve_{applicant_id}_{self.amount}"
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("rt_approve_"):
            return False

        # 権限チェック
        if not any(r.id == ALLOWED_ROLE_ID for r in interaction.user.roles):
            await interaction.response.send_message("❌ 権限がありません（「コイン付与可」ロールが必要です）。", ephemeral=True)
            return False

        # custom_id からデータを復元
        parts = custom_id.replace("rt_approve_", "").split("_")
        target_applicant_id = int(parts[0])
        val = int(parts[1])

        confirm_view = View()
        # 💡 最終確認ボタンにも同じ情報を引き継ぐ
        confirm_btn = Button(
            label="本当によろしいですか？（実行して閉じる）", 
            style=discord.ButtonStyle.danger,
            custom_id=f"rt_confirm_{target_applicant_id}_{val}"
        )
        
        async def confirm_callback(i: discord.Interaction):
            await i.response.defer()
            try:
                # 管理者の残高チェック
                res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
                if not res.data or res.data[0]['coin_count'] < val:
                    return await i.followup.send("❌ あなたの在庫コインが足りません。", ephemeral=True)

                # 1. 申請者へ付与
                self.bot.add_data(target_applicant_id, val)
                
                # 2. 管理者から減算
                self.bot.supabase.table("user_coins").update({
                    "coin_count": res.data[0]['coin_count'] - val
                }).eq("user_id", str(i.user.id)).execute()

                await i.edit_original_response(content=f"✅ {val:,} 枚での買取を最終承認しました。5秒後にチャンネルを削除します。", view=None)
                
                # DM通知
                try:
                    applicant_user = self.bot.get_user(target_applicant_id) or await self.bot.fetch_user(target_applicant_id)
                    if applicant_user:
                        await applicant_user.send(f"🔔 買取完了！{val:,} 枚が付与されました。")
                except: 
                    pass

                await asyncio.sleep(5)
                await i.channel.delete()
            except Exception as e:
                await i.followup.send(f"❌ エラーが発生しました: {e}", ephemeral=True)

        confirm_btn.callback = confirm_callback
        confirm_view.add_item(confirm_btn)
        
        await interaction.response.send_message(
            "⚠️ **最終確認：このままコインを付与してチケットを閉じても本当によろしいですか？**", 
            view=confirm_view, 
            ephemeral=True
        )
        return True


# --- 3. チケット発行パネル（永続化対応版） ---
class RobloxTicketLaunchView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.category_id = 1499380530376999032

    @discord.ui.button(label="買取申請を開始する", style=discord.ButtonStyle.primary, emoji="🤖", custom_id="roblox_trade_start")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        category = guild.get_channel(self.category_id)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        for user_id in [719461059248783401, 718428067340615730]:
            target = guild.get_member(user_id)
            if target: 
                overwrites[target] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await guild.create_text_channel(
            name=f"買取-{interaction.user.display_name}",
            category=category,
            overwrites=overwrites
        )
        
        await interaction.response.send_message(f"✅ {channel.mention} を作成しました。", ephemeral=True)
        
        # 💡 custom_id を設定し、再起動されてもモーダルが確実に開くようにする
        form_view = View(timeout=None)
        form_view.add_item(Button(
            label="ここをタップして申請フォームを入力", 
            style=discord.ButtonStyle.green, 
            custom_id="roblox_form_open_btn"
        ))
        
        await channel.send(f"{interaction.user.mention} さん、下のボタンから詳細を入力してください。", view=form_view)


# --- 4. メインCog ---
class RobloxTrade(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 🛠️ 重複バグを避けるため、コマンド名を変更しました！
    @app_commands.command(name="roblox_trade_panel", description="【管理者用】買取申請ボタンを設置します")
    async def roblox_trade_panel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 権限がありません。", ephemeral=True)
        
        embed = discord.Embed(
            title="🤖 ロブロックス買取受付", 
            description="ロブロックスのアイテムやキャラの買取希望の方はこちら。\n下のボタンを押すと専用チャンネルが開きます。", 
            color=0x3498DB
        )
        await interaction.channel.send(embed=embed, view=RobloxTicketLaunchView(self.bot))
        await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

    # 💡 常駐View（ボタン）が再起動後も正常に動くようにBotへ仕込む処理
    @commands.Cog.listener()
    async def on_ready(self):
        # フォームを開くボタンの永続待機イベント
        class GlobalFormOpenView(View):
            def __init__(self, bot_instance):
                super().__init__(timeout=None)
                self.bot = bot_instance
            @discord.ui.button(label="ここをタップして申請フォームを入力", style=discord.ButtonStyle.green, custom_id="roblox_form_open_btn")
            async def open_modal(self, i: discord.Interaction, b: Button):
                await i.response.send_modal(RobloxTradeModal(self.bot))

        self.bot.add_view(GlobalFormOpenView(self.bot))
        print("✅ ロブロイカサマ防止・買取常駐Viewの登録完了")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: 
            return
        if message.channel.name and message.channel.name.startswith("買取-"):
            if message.attachments:
                await message.channel.send(f"📸 画像を確認しました！\n{ADMIN_USER_MENTIONS} さん、確認お願いします！")

async def setup(bot):
    await bot.add_cog(RobloxTrade(bot))