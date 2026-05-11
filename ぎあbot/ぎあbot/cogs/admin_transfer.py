import discord
from discord import app_commands
from discord.ext import commands

class AdminTransfer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log_channel_id = 1499349163299700836 
        # --- [設定] 配布を許可するロールのIDをここに入れる ---
        self.allowed_role_id = 1499355000185557108 # 作成したロールIDに書き換えてください。

    @app_commands.command(name="give_coin", description="【専用ロール保持者限定】ユーザーにコインを配布します")
    @app_commands.describe(target="配布先のユーザー", amount="配布する枚数")
    async def give_coin(self, interaction: discord.Interaction, target: discord.User, amount: int):
        # 1. ロールチェック
        role = interaction.guild.get_role(self.allowed_role_id)
        if role not in interaction.user.roles:
            return await interaction.response.send_message(f"❌ このコマンドは「{role.name if role else '専用ロール'}」保持者のみ実行可能です。", ephemeral=True)

        if amount <= 0:
            return await interaction.response.send_message("❌ 1枚以上の枚数を指定してください。", ephemeral=True)

        await interaction.response.defer()

        # 2. 管理者の現在の在庫と累計配布数を取得
        res_admin = self.bot.supabase.table("user_coins").select("coin_count, total_distributed").eq("user_id", str(interaction.user.id)).execute()
        
        admin_data = res_admin.data[0] if res_admin.data else {"coin_count": 0, "total_distributed": 0}
        current_inventory = admin_data.get("coin_count", 0)
        current_total_dist = admin_data.get("total_distributed", 0)

        if current_inventory < amount:
            return await interaction.followup.send(f"❌ 在庫不足です（現在: {current_inventory:,}枚）。管理者に連絡してください")

        # 3. データの更新
        new_inventory = current_inventory - amount
        new_total_dist = current_total_dist + amount

        self.bot.supabase.table("user_coins").update({
            "coin_count": new_inventory,
            "total_distributed": new_total_dist
        }).eq("user_id", str(interaction.user.id)).execute()

        # ターゲットにコイン付与
        self.bot.add_data(target.id, amount)

        # 4. 指定されたチャンネルへログ送信
        log_chan = self.bot.get_channel(self.log_channel_id)
        if log_chan:
            # ↓ ここの[cite: 1] を削除しました！
            log_text = f"📢 **{interaction.user.display_name}** さんが **{target.display_name}** さんへ **{amount:,} コイン** を付与しました！"
            
            embed = discord.Embed(title="💰 コイン配布完了報告", description=log_text, color=0x00ff00)
            embed.add_field(name="実行者 (配布担当)", value=interaction.user.mention, inline=True)
            embed.add_field(name="受取者", value=target.mention, inline=True)
            embed.add_field(name="今回の付与枚数", value=f"{amount:,} 枚", inline=False)
            embed.add_field(name="担当者の累計配布数", value=f"📊 **{new_total_dist:,} 枚**", inline=True)
            embed.add_field(name="担当者の残り在庫", value=f"📦 {new_inventory:,} 枚", inline=True)
            
            await log_chan.send(embed=embed)

        await interaction.followup.send(f"✅ {target.mention} さんへの付与が完了しました。")

async def setup(bot):
    await bot.add_cog(AdminTransfer(bot))