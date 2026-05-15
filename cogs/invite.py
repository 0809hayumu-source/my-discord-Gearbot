import discord
from discord.ext import commands
import datetime

class Invite(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.invite_cache = {}  
        self.reward_amount = 100
        self.log_channel_id = 1499009119435362386
        # --- ここをロールIDに変更しました ---
        self.target_role_id = 1495192303936208906 

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            try:
                self.invite_cache[guild.id] = await guild.invites()
            except:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        invites_before = self.invite_cache.get(guild.id, [])
        invites_after = await guild.invites()
        self.invite_cache[guild.id] = invites_after

        inviter_id = None
        for invite in invites_before:
            for after in invites_after:
                if invite.code == after.code and invite.uses < after.uses:
                    inviter_id = invite.inviter.id
                    break
        
        if inviter_id:
            if not hasattr(self.bot, 'pending_invites'):
                self.bot.pending_invites = {}
            # 誰が誰に招待されたかを一時保存
            self.bot.pending_invites[member.id] = inviter_id

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # ロールが付与されたかチェック
        if len(before.roles) < len(after.roles):
            # 新しく追加されたロールを取得
            new_role = next(role for role in after.roles if role not in before.roles)
            
            # IDで判定するので確実！
            if new_role.id == self.target_role_id:
                inviter_id = getattr(self.bot, 'pending_invites', {}).get(after.id)
                
                if inviter_id:
                    # 招待者にコインを付与
                    self.bot.add_data(inviter_id, self.reward_amount)
                    
                    log_chan = self.bot.get_channel(self.log_channel_id)
                    if log_chan:
                        embed = discord.Embed(
                            title="✅ 認証完了おめでとう！",
                            description=f"{after.mention} さんが認証（ロール付与）を完了しました！\n招待者の <@{inviter_id}> さんに報酬をプレゼントします。",
                            color=0x2ecc71
                        )
                        embed.add_field(name="🎁 獲得報酬", value=f"**{self.reward_amount} コイン**")
                        await log_chan.send(embed=embed)
                    
                    # 完了したのでメモから消す
                    del self.bot.pending_invites[after.id]

async def setup(bot):
    await bot.add_cog(Invite(bot))