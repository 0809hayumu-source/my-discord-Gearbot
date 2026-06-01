import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, TextInput, Modal
import asyncio
import datetime
import re

# --- 設定 ---
TICKET_PANEL_CHANNEL_ID = 1502694905817071809  # パネルを設置するチャンネル
INTERMEDIATOR_ROLE_ID = 1502651304823230596    # 🤝 仲介ロールID
AUDIT_LOG_CHANNEL_ID = 1507741830668619927     # 🛑 不正防止ログ用チャンネルID

# 管理者リスト
SILENT_ADMIN_ID = 718428067340615730           # 🤫 メンションなし・参加のみの管理者
MENTION_ADMIN_ID = 719461059248783401          # 🔔 メンションありの管理者


# --- 📝 取引相手と内容を入力するモーダル窓 ---
class TicketInviteModal(Modal, title="🤝 取引相手の招待"):
    target_input = TextInput(
        label="取引相手のユーザーID または メンション",
        placeholder="例: 719461059248783401 または @ユーザー名",
        min_length=1,
        max_length=100,
        required=True
    )

    async def on_submit(self, i: discord.Interaction):
        guild = i.guild
        channel = i.channel
        raw_target = self.target_input.value.strip()
        
        # --- ID抽出ロジック ---
        user_id_match = re.search(r'<@!?(\d+)>', raw_target)
        if user_id_match:
            target_id = int(user_id_match.group(1))
        else:
            id_only_match = re.search(r'^\d+$', raw_target)
            if id_only_match:
                target_id = int(id_only_match.group())
            else:
                return await i.response.send_message("❌ 正しいメンション（@ユーザー名）またはユーザーIDを入力してください。", ephemeral=True)
        
        # --- メンバー取得と検証 ---
        target_member = guild.get_member(target_id)
        if not target_member:
            return await i.response.send_message("❌ サーバー内に指定されたユーザーが見つかりませんでした。", ephemeral=True)

        if target_member.id == i.user.id:
            return await i.response.send_message("❌ 自分自身を取引相手として招待することはできません。", ephemeral=True)

        # --- 権限付与と通知 ---
        await channel.set_permissions(
            target_member,
            read_messages=True,
            send_messages=True,
            attach_files=True
        )

        info_emb = discord.Embed(
            title="📥 取引相手の招待が完了しました",
            color=0x2ecc71,
            timestamp=datetime.datetime.now()
        )
        info_emb.add_field(name="👤 招待された取引相手", value=target_member.mention, inline=False)
        info_emb.set_footer(text=f"設定者: {i.user.display_name}")

        await channel.send(content=f"➕ {i.user.mention} が取引相手として {target_member.mention} を招待しました！", embed=info_emb)
        await i.response.send_message(f"✅ {target_member.display_name} を招待したよ！", ephemeral=True)


# --- 🎮 統合型View（競合を徹底排除したロジック） ---
class TicketCombinedControlView(View):
    def __init__(self, show_invite: bool = False):
        super().__init__(timeout=None)
        self.show_invite = show_invite
        
        # 招待前なら「招待ボタン」を非表示にする
        if not self.show_invite:
            self.remove_item(self.invite_partner)

    # 🟢 ボタン1: 取引相手を招待する
    @discord.ui.button(label="🟢 取引相手を招待する", style=discord.ButtonStyle.success, emoji="➕", custom_id="mm_ticket_invite")
    async def invite_partner(self, i: discord.Interaction, b: Button):
        await i.response.send_modal(TicketInviteModal())

    # ✋ ボタン2: 私が対応します
    @discord.ui.button(label="✋ 私が対応します", style=discord.ButtonStyle.success, emoji="🤝", custom_id="mm_ticket_claim")
    async def claim_ticket(self, i: discord.Interaction, b: Button):
        has_role = any(r.id == INTERMEDIATOR_ROLE_ID for r in i.user.roles)
        is_admin = i.user.id in [SILENT_ADMIN_ID, MENTION_ADMIN_ID] or i.user.guild_permissions.administrator

        if not (has_role or is_admin):
            try:
                return await i.response.send_message("❌ あなたは仲介担当者ではないため、このボタンは押せません。", ephemeral=True)
            except discord.InteractionResponded:
                return await i.followup.send("❌ あなたは仲介担当者ではないため、このボタンは押せません。", ephemeral=True)

        # 担当状態のUIを作成
        b.label = f"担当: {i.user.display_name}"
        b.style = discord.ButtonStyle.secondary
        b.disabled = True

        new_view = TicketCombinedControlView(show_invite=True)
        new_view.children[1].label = b.label
        new_view.children[1].style = b.style
        new_view.children[1].disabled = True

        await i.message.edit(view=new_view)
        
        # 応答の辻褄を合わせるためにdeferを投げておく（エラーは無視）
        try: await i.response.defer()
        except: pass

        claim_emb = discord.Embed(
            description=f"✨ **{i.user.mention} がこの取引の仲介担当になりました！**\nお手数ですが、取引の指示に従って進めてください。",
            color=0x2ecc71
        )
        await i.channel.send(embed=claim_emb)

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

    # 🔒 ボタン3: チケットを閉じる
    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.danger, custom_id="mm_ticket_close")
    async def close_ticket(self, i: discord.Interaction, b: Button):
        try: await i.response.defer()
        except: pass
            
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

        await i.channel.send("⏳ この仲介チャンネルを5秒後に削除します...")
        await asyncio.sleep(5)
        try:
            await i.channel.delete()
        except discord.Forbidden:
            await i.channel.send("❌ チャンネル削除権限がBotにありません。")


# --- 📩 パネルに常駐する『仲介を依頼する』ボタン ---
class TicketLaunchView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🤝 仲介を依頼する", style=discord.ButtonStyle.primary, emoji="📩", custom_id="mm_ticket_open")
    async def open_ticket(self, i: discord.Interaction, b: Button):
        # 💡 deferすら行わず、エラーが出ても無視する「例外処理」のみに絞ります
        try:
            # 既に何らかの応答が完了している場合はこれをスキップ
            if not i.response.is_done():
                await i.response.defer(ephemeral=True)
        except Exception:
            pass

        guild = i.guild
        member = i.user
        
        category_id = getattr(i.client, "TICKET_CATEGORY_ID", None)
        category = guild.get_channel(category_id) if category_id else None
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        role = guild.get_role(INTERMEDIATOR_ROLE_ID)
        if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        silent_admin = guild.get_member(SILENT_ADMIN_ID)
        if silent_admin: overwrites[silent_admin] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        mention_admin = guild.get_member(MENTION_ADMIN_ID)
        if mention_admin: overwrites[mention_admin] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            ticket_channel = await guild.create_text_channel(
                name=f"🤝仲介-{member.display_name}",
                category=category,
                overwrites=overwrites,
                reason=f"仲介チケット作成: {member.name}"
            )
        except Exception as e:
            return await i.followup.send(f"❌ チャンネル作成に失敗しました: {e}", ephemeral=True)

        mention_str = ""
        if role: mention_str += f"{role.mention} "
        mention_str += f"<@{MENTION_ADMIN_ID}>"

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

        emb = discord.Embed(
            title="🤝 仲介依頼を受け付けました",
            description=(
                f"お疲れ様です！{member.mention} さんが仲介を希望しています。\n\n"
                "**【仲介スタッフへのお願い】**\n"
                "対応を開始する際は、下の **「私が対応します」** ボタンを必ず押してください。\n\n"
                "**【依頼者へのお願い】**\n"
                "仲介スタッフが対応ボタンを押すと、ここに **「🟢 取引相手を招待する」** ボタンが出現します！"
            ),
            color=0x3498db
        )

        await ticket_channel.send(content=f"🔔 {mention_str}", embed=emb, view=TicketCombinedControlView(show_invite=False))
        await i.followup.send(f"✅ チケットを作成しました！こちらへどうぞ ➡ {ticket_channel.mention}", ephemeral=True)


# --- ⚙️ Cog本体 ---
class MiddlemanTicket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.TICKET_CATEGORY_ID = 123456789012345678

    @app_commands.command(name="setup_ticket", description="【管理者専用】指定チャンネルに仲介チケットのパネルを設置します")
    @commands.has_permissions(administrator=True)
    async def setup_ticket(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        target_channel = self.bot.get_channel(TICKET_PANEL_CHANNEL_ID)
        if not target_channel:
            return await interaction.followup.send("❌ 設定されたパネル設置用チャンネルが見つかりませんでした。", ephemeral=True)

        emb = discord.Embed(
            title="🤝 仲介サポート窓口",
            description=(
                "ユーザー同士の安全な取引をサポートするために仲介を行います！\n\n"
                "📌 **ご利用方法**\n"
                "下の **「仲介を依頼する」** ボタンを押すると、あなたと仲介人だけが見られる専用の秘密チャンネルが新しく作成されます。"
            ),
            color=0x9b59b6
        )
        
        await target_channel.send(embed=emb, view=TicketLaunchView())
        await interaction.followup.send(f"✅ {target_channel.mention} に仲介チケットパネルを設置したよ！", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketLaunchView())
        self.bot.add_view(TicketCombinedControlView(show_invite=False))
        self.bot.add_view(TicketCombinedControlView(show_invite=True))


async def setup(bot):
    await bot.add_cog(MiddlemanTicket(bot))