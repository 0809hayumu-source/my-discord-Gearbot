import discord
from discord import app_commands
from discord.ext import commands

class AdminTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 除外する運営・特定ユーザーIDリスト
        self.exclude_ids = ["718428067340615730", "719461059248783401"]

    @app_commands.command(name="admin_profit", description="【管理者専用】サーバーの総収支（店長の利益）を確認します")
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_profit(self, interaction: discord.Interaction):
        """
        サーバー内の経済状況を可視化する店長専用コマンド。
        結果はチャンネル内の全員に見える状態で送信されます。
        """
        # ephemeral=False にすることで、チャンネルに残るようになります
        await interaction.response.defer(ephemeral=False)

        try:
            # 1. Supabaseから全ユーザーのコインデータを取得
            res = self.bot.supabase.table("user_coins").select("user_id, monthly_spent, coin_count").execute()
            
            if not res.data:
                return await interaction.followup.send("❌ ユーザーデータが一件も存在しません。")

            # 2. 集計処理（特定のIDを除外）
            filtered_data = [
                row for row in res.data 
                if row.get("user_id") not in self.exclude_ids
            ]

            if not filtered_data:
                return await interaction.followup.send("⚠️ 除外対象以外の一般ユーザーデータが存在しません。")

            total_profit = sum(row.get("monthly_spent", 0) for row in filtered_data)
            total_holding = sum(row.get("coin_count", 0) for row in filtered_data)
            user_count = len(filtered_data)
            
            # 平均保持額
            avg_holding = total_holding / user_count if user_count > 0 else 0

            # 3. Embedの作成
            embed = discord.Embed(
                title="📊 ぎあカジノ 経営指標報告書",
                description="現在の一般ユーザーにおけるコインの流通量と回収状況です。\n（※運営・特定IDのデータは計算から除外済み）",
                color=discord.Color.dark_gold()
            )

            # メイン指標
            embed.add_field(
                name="💰 一般ユーザーからの総利益", 
                value=f"**{total_profit:,} 枚**", 
                inline=False
            )
            
            embed.add_field(
                name="🏦 一般ユーザーの総資産", 
                value=f"{total_holding:,} 枚", 
                inline=True
            )
            
            embed.add_field(
                name="👥 集計対象人数", 
                value=f"{user_count} 名", 
                inline=True
            )

            # 4. 経営アドバイス
            if total_profit > 30000:
                advice = "🔥 **絶好調です！** 回収が順調すぎるため、還元イベントを検討しても良いでしょう。"
                status_emoji = "🤑"
            elif total_profit > 10000:
                advice = "✅ **安定運営です。** 現在の確率設定がうまく機能しています。"
                status_emoji = "📈"
            elif total_profit < 5000:
                advice = "⚠️ **回収不足です。** ユーザーにコインが溜まりすぎているため、回収率の調整を推奨します。"
                status_emoji = "💸"
            else:
                advice = "健全な運営です。適度な勝負が提供されています。"
                status_emoji = "⚖️"

            embed.add_field(name=f"{status_emoji} 店長の分析アドバイス", value=advice, inline=False)
            
            # 5. インフレ警告
            if avg_holding > 5000:
                embed.add_field(
                    name="⚠️ 警告：インフレの兆候", 
                    value="1人あたりの平均所持金が高すぎます。コインを消費させる施策が必要です。",
                    inline=False
                )

            embed.set_footer(text=f"実行者: {interaction.user.display_name} | 集計完了")

            # 結果を全員（チャンネル内）に見えるように送信
            await interaction.followup.send(embed=embed)

        except Exception as e:
            print(f"Admin Profit Error: {e}")
            await interaction.followup.send(f"❌ エラーが発生しました。\n`{e}`")

    # 権限エラー（管理者以外が実行した場合）のハンドリング
    @admin_profit.error
    async def admin_profit_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ このコマンドは管理者権限を持つユーザーのみ実行可能です。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminTools(bot))