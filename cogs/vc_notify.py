import discord
from discord.ext import commands

# --- [設定] ---
MONITOR_VC_ID = 1495342014382739556      # 監視するボイスチャンネルID
NOTIFY_TEXT_CH_ID = 1495323410606063657 # 通知を送るテキストチャンネルID
TARGET_USER_IDS = [719461059248783401, 718428067340615730] # 堀内さんとAさんのID

class VCNotify(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # 指定のユーザーが、指定のVCに入ったかチェック
        if member.id in TARGET_USER_IDS and after.channel and after.channel.id == MONITOR_VC_ID:
            # 前の状態がそのVCではなかった場合（入室の瞬間）
            if not before.channel or before.channel.id != MONITOR_VC_ID:
                channel = self.bot.get_channel(NOTIFY_TEXT_CH_ID)
                if channel:
                    await channel.send(f"@everyone\n📢 **{member.display_name}** がボイスチャンネルに入りました！！")

async def setup(bot):
    await bot.add_cog(VCNotify(bot))