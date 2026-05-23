import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
import asyncio
import datetime

# --- 設定 ---
TICKET_PANEL_CHANNEL_ID = 1502694905817071809  # パネルを設置するチャンネル
INTERMEDIATOR_ROLE_ID = 1502651304823230596    # 🤝 仲介ロールID
AUDIT_LOG_CHANNEL_ID = 1507741830668619927     # 🛑 不正防止ログ用チャンネルID

# 管理者リスト
SILENT_ADMIN_ID = 718428067340615730           # 🤫 メンションなし・参加のみの管理者
MENTION_ADMIN_ID = 719461059248783401          # 🔔 メンションありの管理者


class TicketCloseView(View):
    """チケット内にある『閉じる』ボタン"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.danger, custom_id="mm_ticket_close")
    async def close_ticket(self, i: discord.Interaction, b: Button):
        await i.response.defer()
        
        # 🛑 ログチャンネルへチケットクローズの記録を送信
        try:
            log_channel = i.guild.get_channel(AUDIT_LOG_CHANNEL_ID)
            if log_channel:
                emb = discord.Embed(
                    title="🔒 仲介チケット終了 (クローズ)",
                    description=f"**実行者:** {i.user.mention} ({i.user.name})\n**チャンネル:** `{i.channel.name}`\n\n※このログは不正防止のために自動記録されています。",
                    color=0x34495e,
                    timestamp=datetime.datetime.now()
                )
                await log_channel.send(embed=emb)
        except Exception as e:
            print(f"ログ送信失敗: {e}")

        await i.followup.send("⏳ この仲介チャンネルを5秒後に削除します...")
        await asyncio.sleep(5)
        try:
            await i.channel.delete()
        except discord.Forbidden:
            await i.followup.send("❌ チャンネル削除権限がBotにありません。", ephemeral=True)


class TicketActionView(View):
    """チケットチャンネル内の案内と一緒に送られる『対応する』ボタン"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✋ 私が対応します", style=discord.ButtonStyle.success, emoji="🤝", custom_id="mm_ticket_claim")
    async def claim_ticket(self, i: discord.Interaction, b: Button):
        # 仲介ロールを持っているか、指定の管理者であるかチェック
        has_role = any(r.id == INTERMEDIATOR_ROLE_ID for r in i.user.roles)
        is_admin = i.user.id in [SILENT_ADMIN_ID, MENTION_ADMIN_ID] or i.user.guild_permissions.administrator

        if not (has_role or is_admin):
            return await i.response.send_message("❌ あなたは仲介担当者ではないため、このボタンは押せません。", ephemeral=True)

        await i.response.defer()

        # ボタンを無効化して「対応中」の表記にアップデート
        b.label = f"担当: {i.user.display_name}"
        b.style = discord.ButtonStyle.secondary
        b.disabled = True
        
        # 既存のメッセージを更新して、誰が担当になったかを明示する
        await i.message.edit(view=self)

        # チャンネル内に担当者が決まったアナウンスを送信
        claim_emb = discord.Embed(
            description=f"✨ **{i.user.mention} がこの取引の仲介担当になりました！**\nお手数ですが、取引の指示に従って進めてください。",
            color=0x2ecc71
        )
        await i.channel.send(embed=claim_emb)

        # 🛑 不正防止ログ用チャンネルへ「誰が対応を開始したか」を記録
        try:
            log_channel = i.guild.get_channel(AUDIT_LOG_CHANNEL_ID)
            if log_channel:
                emb = discord.Embed(
                    title="🤝 仲介対応スタート",
                    description=(
                        f"**担当仲介人:** {i.user.mention} ({i.user.name})\n"
                        f"**対応チャンネル:** {i.channel.mention} (`{i.channel.name}`)\n"
                        f"**対応開始時間:** <t:{int(datetime.datetime.now().timestamp())}:F>"
                    ),
                    color=0x2ecc71,
                    timestamp=datetime.datetime.now()
                )
                await log_channel.send(embed=emb)
        except Exception as e:
            print(f"ログ送信失敗: {e}")


class TicketLaunchView(View):
    """常駐する『仲介を依頼する』ボタン"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🤝 仲介を依頼する", style=discord.ButtonStyle.primary, emoji="📩", custom_id="mm_ticket_open")
    async def open_ticket(self, i: discord.Interaction, b: Button):
        await i.response.defer(ephemeral=True)

        guild = i.guild
        member = i.user
        
        # 🚨 カテゴリーIDの取得（メイン設定のTICKET_CATEGORY_IDを参照。なければNoneでルートに作成）
        category_id = getattr(i.client, "TICKET_CATEGORY_ID", None)
        category = guild.get_channel(category_id) if category_id else None
        
        # 閲覧権限の設定 (@everyoneは非表示、作成者とBotは表示)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # 仲介ロールの権限追加
        role = guild.get_role(INTERMEDIATOR_ROLE_ID)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # 🤫 メンションなし管理者（718428067340615730）の権限を追加（参加のみ）
        silent_admin = guild.get_member(SILENT_ADMIN_ID)
        if silent_admin:
            overwrites[silent_admin] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # 🔔 メンションあり管理者（719461059248783401）の権限を追加
        mention_admin = guild.get_member(MENTION_ADMIN_ID)
        if mention_admin:
            overwrites[mention_admin] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # チャンネル作成
        try:
            ticket_channel = await guild.create_text_channel(
                name=f"🤝仲介-{member.display_name}",
                category=category,
                overwrites=overwrites,
                reason=f"仲介チケット作成: {member.name}"
            )
        except Exception as e:
            return await i.followup.send(f"❌ チャンネル作成に失敗しました: {e}", ephemeral=True)

        # 🤫 718428067340615730 はメンションから除外し、それ以外をメンション
        mention_str = ""
        if role:
            mention_str += f"{role.mention} "
        mention_str += f"<@{MENTION_ADMIN_ID}>"  # 719461059248783401 のみメンション

        # 🛑 不正防止ログへ「誰がチケットを開いたか」の初期ログを送信
        try:
            log_channel = guild.get_channel(AUDIT_LOG_CHANNEL_ID)
            if log_channel:
                emb = discord.Embed(
                    title="📩 新規仲介チケット発行",
                    description=(
                        f"**依頼者:** {member.mention} ({member.name})\n"
                        f"**作成されたチャンネル:** {ticket_channel.mention}\n"
                        f"**参加管理者（サイレント）:** <@{SILENT_ADMIN_ID}>"
                    ),
                    color=0x3498db,
                    timestamp=datetime.datetime.now()
                )
                await log_channel.send(embed=emb)
        except Exception as e:
            print(f"ログ送信失敗: {e}")

        # チケット内の案内メッセージ設定
        emb = discord.Embed(
            title="🤝 仲介依頼を受け付けました",
            description=(
                f"お疲れ様です！{member.mention} さんが仲介を希望しています。\n\n"
                "**【依頼者へのお願い】**\n"
                "仲介スタッフが来てボタンを押すまで、ここに **「取引相手のユーザー名」** や **「取引したい内容」** をあらかじめ書き込んでお待ちください。\n\n"
                "**【仲介スタッフへのお願い】**\n"
                "対応を開始する際は、下の **「私が対応します」** ボタンを必ず押してください。"
            ),
            color=0x3498db
        )

        # チャンネル内にボタン（対応する・閉じる）を設置した案内を送信
        combined_view = View(timeout=None)
        # 1行目に「対応します」ボタン、2行目に「チケットを閉じる」ボタンを綺麗に配置
        action_btn = TicketActionView().children[0]
        close_btn = TicketCloseView().children[0]
        combined_view.add_item(action_btn)
        combined_view.add_item(close_btn)

        await ticket_channel.send(content=f"🔔 {mention_str}", embed=emb, view=combined_view)
        await i.followup.send(f"✅ チケットを作成しました！こちらへどうぞ ➡ {ticket_channel.mention}", ephemeral=True)


class MiddlemanTicket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # カテゴリIDをクラスを跨いで参照できるようにbotに持たせる（もし使う場合用、不要なら1234...のまま直接上に書いてもOK）
        self.bot.TICKET_CATEGORY_ID = 123456789012345678  # 🚨 必要に応じてカテゴリIDを入れてね

    @app_commands.command(name="setup_ticket", description="【管理者専用】指定チャンネルに仲介チケットのパネルを設置します")
    @commands.has_permissions(administrator=True)
    async def setup_ticket(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        target_channel = self.bot.get_channel(TICKET_PANEL_CHANNEL_ID)
        if not target_channel:
            return await interaction.followup.send("❌ 設定されたパネル設置用チャンネルが見つかりませんでした。IDを確認してください。", ephemeral=True)

        emb = discord.Embed(
            title="🤝 仲介サポート窓口",
            description=(
                "ユーザー同士の安全な取引をサポートするために仲介を行います！\n\n"
                "📌 **ご利用方法**\n"
                "下の **「仲介を依頼する」** ボタンを押すと、あなたと仲介人だけが見られる専用の秘密チャンネルが新しく作成されます。\n\n"
                "⚠️ **注意**\n"
                "いたずらでのチケット作成はお控えください。"
            ),
            color=0x9b59b6
        )
        
        await target_channel.send(embed=emb, view=TicketLaunchView())
        await interaction.followup.send(f"✅ {target_channel.mention} に仲介チケットパネルを設置したよ！", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        # 永続化ビューに「対応する」用のカスタムIDを持つボタンも追加
        self.bot.add_view(TicketLaunchView())
        
        # チケット内でバラバラに生成されるボタンもカスタムIDで認識できるように登録
        dynamic_view = View(timeout=None)
        dynamic_view.add_item(TicketActionView().children[0])
        dynamic_view.add_item(TicketCloseView().children[0])
        self.bot.add_view(dynamic_view)


async def setup(bot):
    await bot.add_cog(MiddlemanTicket(bot))