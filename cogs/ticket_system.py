import discord
from discord import app_commands, ui
from discord.ext import commands
import datetime

# --- 設定項目 ---
ADMIN_USER_ID = 719461059248783401   # 👈 指定された管理者のユーザーID
LOG_CHANNEL_ID = 1506486213656314016 # ログチャンネルID

class TicketCloseView(ui.View):
    """作成された個別チケットスレッド内にある『閉じる』ボタン"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="このチケットを閉じる", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="pay_ticket_close")
    async def close_button(self, i: discord.Interaction, b: ui.Button):
        # 👑 押した人が指定の管理者ID（あなた）かチェック
        if i.user.id != ADMIN_USER_ID:
            # 管理者以外が押した場合は、本人だけにエラーを表示して処理を止める
            return await i.response.send_message("❌ このチケットを閉じる権限はありません。（管理者専用）", ephemeral=True)

        # 管理者が押した場合のみ、ここから下の処理が進む
        await i.response.defer()
        await i.followup.send("🔒 管理者によってこのチケットはアーカイブ（クローズ）されました。")
        
        # 📝 ログ送信処理（チケットクローズ）
        log_chan = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_chan:
            log_emb = discord.Embed(
                title="🔒 チケットクローズ記録",
                description=(
                    f"**実行者:** {i.user.mention} (`{i.user.id}`)\n"
                    f"**チャンネル:** {i.channel.mention if hasattr(i.channel, 'mention') else i.channel.name}\n"
                    f"**日時:** <t:{int(datetime.datetime.now().timestamp())}:F>"
                ),
                color=0xff0000
            )
            try:
                await log_chan.send(embed=log_emb)
            except Exception as e:
                print(f"⚠️ クローズログ送信失敗: {e}")

        # スレッドをアーカイブして編集不可にする
        if isinstance(i.channel, discord.Thread):
            await i.channel.edit(archived=True, locked=True)

class PayTicketPanelView(ui.View):
    """チャンネルに常駐させる「チケット発行」パネルのボタン"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="Payチケットを発行する", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="pay_ticket_create")
    async def create_ticket(self, i: discord.Interaction, b: ui.Button):
        # 処理中メッセージ（本人限定）
        await i.response.defer(ephemeral=True)

        if not isinstance(i.channel, discord.TextChannel):
            return await i.followup.send("❌ このチャンネルでは実行できません。", ephemeral=True)

        thread_name = f"pay-ticket-{i.user.name}"
        
        try:
            # 1. プライベートスレッドを作成
            thread = await i.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                invitable=False  # メンバーが勝手に他の人を招待できないように制限
            )
            
            # 2. 発行した一般ユーザーを招待
            await thread.add_user(i.user)
            
            # 3. 指定された管理者IDのユーザーをスレッドに招待 ✨変更点
            admin_user = i.guild.get_member(ADMIN_USER_ID)
            if admin_user:
                await thread.add_user(admin_user)
                admin_mention = admin_user.mention
            else:
                # 万が一、Botのキャッシュにない場合はfetchして招待
                try:
                    admin_user = await i.guild.fetch_member(ADMIN_USER_ID)
                    await thread.add_user(admin_user)
                    admin_mention = admin_user.mention
                except:
                    admin_mention = f"<@{ADMIN_USER_ID}>"

            # 4. スレッドの中に専用の案内 embed と「閉じる」ボタンを送信
            emb = discord.Embed(
                title=f"🎫 {i.user.display_name} さんの専用取引チケット",
                description=(
                    f"ユーザー: {i.user.mention}\n"
                    f"対応スタッフ: {admin_mention}\n\n"
                    "**【取引の流れ】**\n"
                    "1. この画面でお手持ちのPayPayの送金リンクと金額を提示してください。\n"
                    "2. 管理者が確認後、対応を行います。\n"
                    "3. 取引がすべて完了したら、下のボタンを押してチケットを閉じてください。※完了するまでチケットを閉じないでください。"
                ),
                color=0x00ffaa
            )
            
            msg = await thread.send(content=f"{i.user.mention} {admin_mention}", embed=emb, view=TicketCloseView(self.bot))
            await msg.pin()

            # パネルを押した本人への完了通知
            await i.followup.send(f"✅ 専用のチケット画面を作成しました！\nこちらから移動してください 👉 {thread.mention}", ephemeral=True)

            # 📝 ログ送信処理（チケット作成）
            log_chan = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_chan:
                log_emb = discord.Embed(
                    title="🎫 チケット作成記録",
                    description=(
                        f"**作成者:** {i.user.mention} (`{i.user.id}`)\n"
                        f"**担当管理者:** {admin_mention}\n"
                        f"**作成されたスレッド:** {thread.mention}\n"
                        f"**日時:** <t:{int(datetime.datetime.now().timestamp())}:F>"
                    ),
                    color=0x00ff00
                )
                try:
                    await log_chan.send(embed=log_emb)
                except Exception as e:
                    print(f"⚠️ 作成ログ送信失敗: {e}")

        except Exception as e:
            print(f"⚠️ チケット作成エラー: {e}")
            await i.followup.send("❌ チケットの作成に失敗しました。Botの権限（スレッドの管理権限など）を確認してください。", ephemeral=True)


class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ユーザーがチケットを発行するための「パネル」を設置するコマンド
    @app_commands.command(name="pay_panel", description="【管理者専用】Payチケット発行パネルを設置します")
    @commands.has_permissions(administrator=True) # サーバー管理者のみ実行可能
    async def spawn_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        emb = discord.Embed(
            title="💳 PayPayマネラ➤PayPayマネー取引88%",
            description=(
                "PayPayマネーライトをPayPayマネー（現金化）に換金できます\n"
                "下のボタンを押して取引チケットを発行してください。\n\n"
                "⚠️ **ボタンを押すと、あなたと管理者しか見られない専用の非公開スレッドが自動で作られます。**"
            ),
            color=0x0099ff
        )
        await interaction.channel.send(embed=emb, view=PayTicketPanelView(self.bot))
        await interaction.followup.send("✅ 取引パネルを設置しました！", ephemeral=True)


async def setup(bot):
    await bot.add_cog(TicketSystem(bot))