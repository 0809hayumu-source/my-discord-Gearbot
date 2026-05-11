import discord
from discord import app_commands
from discord.ext import commands

# --- 設定：ランキングに載せない管理者のIDリスト ---
EXCLUDE_IDS = [
    719461059248783401,  # あなたID
    718428067340615730,# 他にも除外したい管理者がいればここに追加（カンマ区切り）
    718428067340615730,
    719461059248783401,
    692399279851044906,
]

class Ranking(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        
        words = {
            "ランキング": "all",
            "コインランキング": "coin",
            "チケットランキング": "ticket",
            "週間ランキング": "weekly",
            "月間ランキング": "monthly",
            "消費ランキング": "spent"
        }
        
        if message.content in words:
            await self.show_ranking(message, mode=words[message.content])

    async def show_ranking(self, target, mode="all"):
        try:
            embed = discord.Embed(title="🏆 ぎあBot ランキングボード", color=0xFFD700)

            # --- 💰 総合所持 ---
            if mode in ["all", "coin"]:
                res = self.bot.supabase.table("user_coins").select("user_id, coin_count").order("coin_count", desc=True).limit(20).execute()
                embed.add_field(name="💰 コイン所持TOP5", value=await self.format_rank_data(res.data, "coin_count", "枚"), inline=False)

            # --- 🎟️ チケット所持 ---
            if mode in ["all", "ticket"]:
                res = self.bot.supabase.table("user_tickets").select("user_id, count").order("count", desc=True).limit(20).execute()
                embed.add_field(name="🎟️ チケット所持TOP5", value=await self.format_rank_data(res.data, "count", "枚"), inline=False)

            # --- 💸 週間消費 (太客) ---
            if mode in ["all", "weekly", "spent"]:
                res = self.bot.supabase.table("user_coins").select("user_id, weekly_spent").order("weekly_spent", desc=True).limit(20).execute()
                embed.add_field(name="💸 週間消費TOP5", value=await self.format_rank_data(res.data, "weekly_spent", "枚"), inline=False)

            # --- 👑 月間消費 (覇者) ---
            if mode in ["all", "monthly"]:
                res = self.bot.supabase.table("user_coins").select("user_id, monthly_spent").order("monthly_spent", desc=True).limit(20).execute()
                embed.add_field(name="👑 月間消費TOP5 (今月の覇者)", value=await self.format_rank_data(res.data, "monthly_spent", "枚"), inline=False)

            embed.set_footer(text="※運営チームはランキングから除外されています。")
            await (target.response.send_message(embed=embed) if isinstance(target, discord.Interaction) else target.reply(embed=embed))

        except Exception as e:
            print(f"Ranking Error: {e}")
            await (target.response.send_message("❌ 取得失敗") if isinstance(target, discord.Interaction) else target.reply("❌ 取得失敗"))

    async def format_rank_data(self, data, column_name, unit):
        if not data: return "データなし"
        
        lines = []
        rank_count = 1
        
        for row in data:
            user_id = int(row['user_id'])
            
            # --- 🛡️ 除外リストに入っているIDはスキップ ---
            if user_id in EXCLUDE_IDS:
                continue
                
            try:
                user = await self.bot.fetch_user(user_id)
                name = user.display_name
            except: 
                name = f"不明({user_id})"
            
            val = row.get(column_name, 0)
            if val <= 0: continue # 0以下の人は表示しない
            
            medal = "🥇" if rank_count == 1 else "🥈" if rank_count == 2 else "🥉" if rank_count == 3 else f"**{rank_count}位**"
            lines.append(f"{medal} {name}: **{val:,} {unit}**")
            
            rank_count += 1
            if rank_count > 5: # 5位まで表示したら終了
                break
                
        return "\n".join(lines) if lines else "データなし"

    # 管理者用リセットコマンド（変更なし）
    @app_commands.command(name="reset_ranking", description="ランキングリセット")
    @app_commands.describe(type="どちらをリセットするか")
    @app_commands.choices(type=[
        app_commands.Choice(name="週間(weekly)", value="weekly"),
        app_commands.Choice(name="月間(monthly)", value="monthly")
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_ranking(self, interaction: discord.Interaction, type: str):
        if type == "weekly":
            self.bot.supabase.table("user_coins").update({"weekly_gain": 0, "weekly_spent": 0}).neq("user_id", "0").execute()
            await interaction.response.send_message("✅ 週間ランキングをリセットしました。")
        else:
            self.bot.supabase.table("user_coins").update({"monthly_spent": 0}).neq("user_id", "0").execute()
            await interaction.response.send_message("✅ 月間ランキングをリセットしました。")

async def setup(bot):
    await bot.add_cog(Ranking(bot))