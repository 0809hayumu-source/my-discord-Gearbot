import discord
from discord.ext import commands
from datetime import datetime, timedelta

class AdminLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 指定された管理者専用ログチャンネルID
        self.admin_log_channel_id = 1499016200372490331
        # 認証ロールID
        self.target_role_id = 1495192303936208906 
        # 連続招待の監視用
        self.recent_invites = {} 

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # ロールが付与されたかチェック
        if len(before.roles) < len(after.roles):
            new_role = next(role for role in after.roles if role not in before.roles)
            
            # 認証ロールが付与された場合のみ動作
            if new_role.id == self.target_role_id:
                # invite.pyで記録した招待者IDを取得
                inviter_id = getattr(self.bot, 'pending_invites', {}).get(after.id)
                admin_chan = self.bot.get_channel(self.admin_log_channel_id)
                
                if admin_chan:
                    is_suspicious = False
                    warning_reasons = []

                    # --- 1. アカウント作成日チェック（7日以内は警告） ---
                    # Discord公式のユーザーIDから作成日時を計算
                    account_age = datetime.now(after.created_at.tzinfo) - after.created_at
                    if account_age.days < 7:
                        is_suspicious = True
                        warning_reasons.append(f"⚠️ **新規作成アカウント** (作成から{account_age.days}日)")

                    # --- 2. 短時間の連続認証チェック ---
                    if inviter_id:
                        now = datetime.now()
                        if inviter_id not in self.recent_invites:
                            self.recent_invites[inviter_id] = []
                        
                        # 直近1時間の記録のみ保持
                        self.recent_invites[inviter_id] = [t for t in self.recent_invites[inviter_id] if now - t < timedelta(hours=1)]
                        self.recent_invites[inviter_id].append(now)

                        # 1時間に3人以上認証させたら警告
                        if len(self.recent_invites[inviter_id]) >= 3:
                            is_suspicious = True
                            warning_reasons.append(f"⚠️ **短時間での連続認証** (直近1時間で{len(self.recent_invites[inviter_id])}人目)")

                    # ログの作成
                    title = "🚨 認証・招待詳細ログ"
                    if is_suspicious:
                        title += " 【⚠️違反の疑い】"
                    
                    embed = discord.Embed(
                        title=title,
                        color=0xff0000 if is_suspicious else 0x2f3136, # 怪しい場合は赤色
                        timestamp=datetime.now()
                    )

                    if is_suspicious:
                        embed.add_field(name="🚩 警告フラグ", value="\n".join(warning_reasons), inline=False)

                    # 招待者の詳細（報酬を受け取った側）
                    if inviter_id:
                        embed.add_field(
                            name="👤 招待者 (報酬付与先)",
                            value=f"メンバー: <@{inviter_id}>\nID: `{inviter_id}`",
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name="👤 招待者",
                            value="不明（直接参加、またはBot再起動前の参加）",
                            inline=False
                        )

                    # 参加者本人（認証を終えた側）
                    embed.add_field(
                        name="🆕 認証した人",
                        value=f"メンバー: {after.mention}\nID: `{after.id}`",
                        inline=False
                    )

                    embed.set_footer(text="IDは固定値です。不正調査にご活用ください。")
                    await admin_chan.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AdminLogger(bot))