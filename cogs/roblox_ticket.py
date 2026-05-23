import discord
from discord import app_commands, ui
from discord.ext import commands
import datetime

# --- 設定項目 ---
ADMIN_USER_ID = 719461059248783401   # 管理者のユーザーID
LOG_CHANNEL_ID = 1506536335190790306 # 👈 ロブロックスチケット用のログチャンネルID

class RobloxTicketCloseView(ui.View):
    """作成された個別チケットスレッド内にある『閉じる』ボタン"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="このチケットを閉じる", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="roblox_ticket_close")
    async def close_button(self, i: discord.Interaction, b: ui.Button):
        # 👑 押した人が指定の管理者IDかチェック
        if i.user.id != ADMIN_USER_ID:
            return await i.response.send_message("❌ このチケットを閉じる権限はありません。（管理者専用）", ephemeral=True)

        await i.response.defer()
        await i.followup.send("🔒 管理者によってこのチケットはアーカイブ（クローズ）されました。")
        
        # 📝 ログ送信処理（チケットクローズ）
        log_chan = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_chan:
            log_emb = discord.Embed(
                title="🔒 ロブロチケット クローズ記録",
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
                print(f"⚠️ ロブロクローズログ送信失敗: {e}")

        # スレッドをアーカイブして編集不可にする
        if isinstance(i.channel, discord.Thread):
            await i.channel.edit(archived=True, locked=True)

class RobloxTicketPanelView(ui.View):
    """チャンネルに常駐させる「チケット発行」パネルのボタン"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="交換チケットを発行する", style=discord.ButtonStyle.success, emoji="🤖", custom_id="roblox_ticket_create")
    async def create_ticket(self, i: discord.Interaction, b: ui.Button):
        await i.response.defer(ephemeral=True)

        if not isinstance(i.channel, discord.TextChannel):
            return await i.followup.send("❌ このチャンネルでは実行できません。", ephemeral=True)

        thread_name = f"rbx-{i.user.name}"
        
        try:
            # 1. プライベートスレッドを作成
            thread = await i.channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                invitable=False
            )
            
            # 2. 発行したユーザーを招待
            await thread.add_user(i.user)
            
            # 3. 管理者をスレッドに招待
            admin_user = i.guild.get_member(ADMIN_USER_ID)
            if admin_user:
                await thread.add_user(admin_user)
                admin_mention = admin_user.mention
            else:
                try:
                    admin_user = await i.guild.fetch_member(ADMIN_USER_ID)
                    await thread.add_user(admin_user)
                    admin_mention = admin_user.mention
                except:
                    admin_mention = f"<@{ADMIN_USER_ID}>"

            # 4. スレッドの中に専用の案内 embed と「閉じる」ボタンを送信
            emb = discord.Embed(
                title=f"🤖 {i.user.display_name} さんのロブロックス交換窓口",
                description=(
                    f"ユーザー: {i.user.mention}\n"
                    f"対応スタッフ: {admin_mention}\n\n"
                    "**【取引の流れ】**\n"
                    "1. 交換したいキャラクターやアイテム、アカウントの詳細情報をここに提示してください。\n"
                    "2. 管理者が内容を確認し、交換の手続きを進めます。\n"
                    "3. 取引がすべて安全に完了したら、下のボタンを押してチケットを閉じてください。"
                ),
                color=0x00ff77
            )
            
            msg = await thread.send(content=f"{i.user.mention} {admin_mention}", embed=emb, view=RobloxTicketCloseView(self.bot))
            await msg.pin()

            await i.followup.send(f"✅ 専用の交換チケット画面を作成しました！\nこちらから移動してください 👉 {thread.mention}", ephemeral=True)

            # 📝 ログ送信処理（チケット作成）
            log_chan = self.bot.get_channel(LOG_CHANNEL_ID)
            if log_chan:
                log_emb = discord.Embed(
                    title="🤖 ロブロチケット 作成記録",
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
                    print(f"⚠️ ロブロ作成ログ送信失敗: {e}")

        except Exception as e:
            print(f"⚠️ ロブロチケット作成エラー: {e}")
            await i.followup.send("❌ チケットの作成に失敗しました。Botの権限を確認してください。", ephemeral=True)


class RobloxTicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 設置コマンド
    @app_commands.command(name="roblox_panel", description="【管理者専用】ロブロックス交換パネルを設置します")
    @commands.has_permissions(administrator=True)
    async def spawn_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        emb = discord.Embed(
            title="🤖 Roblox キャラクター・アイテム交換窓口",
            description=(
                "ロブロックスのキャラクターやゲーム内アイテムの交換・お取引をご希望の方は、"
                "下のボタンを押して専用チケットを発行してください。\n\n"
                "⚠️ **あなたと管理者しか見られない非公開スレッドが作成されます。詐欺防止のため、必ずここでお取引をお願いします。**"
            ),
            color=0x00ff77
        )
        await interaction.channel.send(embed=emb, view=RobloxTicketPanelView(self.bot))
        await interaction.followup.send("✅ ロブロックス交換パネルを設置しました！", ephemeral=True)


async def setup(bot):
    await bot.add_cog(RobloxTicketSystem(bot))