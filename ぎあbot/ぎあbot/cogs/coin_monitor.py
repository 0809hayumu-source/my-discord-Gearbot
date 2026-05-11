import discord
from discord import app_commands, ui
from discord.ext import commands
import datetime

# --- 設定 ---
# 実行を許可する管理者のユーザーIDリスト（あなたのIDや他の管理者のIDを入れてください）
ALLOWED_ADMIN_IDS = [718428067340615730, 719461059248783401] 

class CoinMonitorView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None) # パネルが消えないようにタイムアウトなし
        self.bot = bot

    async def create_monitor_embed(self):
        # Supabaseから「1コイン以上」持っているユーザーを、コインが多い順に取得
        # .gt('coin_count', 0) は 0より大きいデータを指定
        res = self.bot.supabase.table("user_coins") \
            .select("*") \
            .gt("coin_count", 0) \
            .order("coin_count", desc=True) \
            .execute()
        
        data = res.data

        emb = discord.Embed(
            title="💰 全ユーザー・コイン監視パネル",
            description="現在1コイン以上所持しているユーザーのリストです",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )

        if not data:
            emb.description = "現在コインを所持しているユーザー（1枚以上）はいません。"
        else:
            list_text = ""
            for i, user_data in enumerate(data, 1):
                u_id = int(user_data['user_id'])
                coins = user_data['coin_count']
                
                # ユーザー情報の取得（表示名 @ユーザー名）
                user = self.bot.get_user(u_id)
                if user:
                    member_display = f"{user.display_name} (@{user.name})"
                else:
                    member_display = f"不明なユーザー (`{u_id}`)"
                
                # 100万枚以上は警告マークを表示
                warn = "⚠️" if coins >= 1000000 else ""
                
                # 1行分のテキスト作成
                line = f"{i}. **{member_display}**\n　┗ `{coins:,}` 枚 {warn}\n"
                
                # Discordの1フィールドの制限（1024文字）に収まるかチェック
                if len(list_text) + len(line) > 1000:
                    list_text += "…（これ以降は人数が多いため省略）…"
                    break
                
                list_text += line
            
            emb.add_field(name="所持者ランキング（降順）", value=list_text, inline=False)
        
        # 統計情報の計算
        total_users = len(data)
        total_sum = sum(u['coin_count'] for u in data)
        
        emb.set_footer(text=f"合計所持者: {total_users}名 | 市場総額: {total_sum:,}枚")
        return emb

    @ui.button(label="最新の情報に更新", style=discord.ButtonStyle.green, emoji="🔄")
    async def refresh(self, interaction: discord.Interaction, btn: ui.Button):
        # 権限チェック
        if interaction.user.id not in ALLOWED_ADMIN_IDS:
            return await interaction.response.send_message("❌ この操作は許可された管理者のみ可能です。", ephemeral=True)
        
        # 編集して更新
        await interaction.response.edit_message(embed=await self.create_monitor_embed())

class AdminMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="coin_monitor", description="【管理者用】1コイン以上所持しているユーザーを一覧表示します")
    async def coin_monitor(self, interaction: discord.Interaction):
        # 権限チェック
        if interaction.user.id not in ALLOWED_ADMIN_IDS:
            return await interaction.response.send_message("❌ 実行権限がありません。", ephemeral=True)

        view = CoinMonitorView(self.bot)
        emb = await view.create_monitor_embed()
        await interaction.response.send_message(embed=emb, view=view)

async def setup(bot):
    await bot.add_cog(AdminMonitor(bot))