import discord

# 特製：最凶ランク設定
RANK_SETTINGS = {
    "Bronze": {"threshold": 10000, "next": "Silver", "reward": 500, "carry": 0.1, "role_id": 1502496400934436917},
    "Silver": {"threshold": 30000, "next": "Gold", "reward": 3000, "carry": 0.1, "role_id": 1502497008408334386},
    "Gold":   {"threshold": 150000, "next": "Platinum", "reward": 10000, "carry": 0.1, "role_id": 1502497137508880505},
    "Platinum":{"threshold": 400000, "next": "Diamond", "reward": 30000, "carry": 0.1, "role_id": 1502497298037604491},
    "Diamond": {"threshold": 700000, "next": "Master", "reward": 60000, "carry": 0.1, "role_id": 1502497578141487174},
    "Master":  {"threshold": 1500000, "next": "Legend", "reward": 100000, "carry": 0.1, "role_id": 1502604006483165265}, # ロール未定義ならNone
    "Legend":  {"threshold": 3000000, "next": "???", "reward": 200000, "carry": 0.1, "role_id": 1502604149622313041},
    "???":     {"threshold": 10000000, "next": "MAX", "reward": 1000000, "carry": 0.1, "role_id": None},
}

async def process_rank_system(bot, user_id, spent_amount):
    user_id_str = str(user_id)
    
    # 1. DBからユーザーデータを取得
    res = bot.supabase.table("user_coins").select("*").eq("user_id", user_id_str).execute()
    if not res.data:
        return None 
    
    data = res.data[0]
    current_rank = data.get("rank", "Bronze")
    monthly_spent = data.get("monthly_spent", 0)
    weekly_spent = data.get("weekly_spent", 0)
    coin_count = data.get("coin_count", 0)
    
    # 2. 進捗加算と判定
    settings = RANK_SETTINGS.get(current_rank, RANK_SETTINGS["Bronze"])
    new_spent = monthly_spent + spent_amount
    new_weekly = weekly_spent + spent_amount
    new_coins = coin_count - spent_amount
    
    reward_msg = ""
    target_rank = current_rank
    
    if new_spent >= settings["threshold"]:
        # 🎊 ランクアップ！
        next_rank = settings["next"]
        reward = settings["reward"]
        
        next_goal = RANK_SETTINGS.get(next_rank, {}).get("threshold", 10000)
        carry_over = int(next_goal * settings["carry"])
        
        bot.supabase.table("user_coins").update({
            "coin_count": new_coins + reward,
            "rank": next_rank,
            "monthly_spent": carry_over,
            "weekly_spent": new_weekly,
            "last_reward_rank": current_rank
        }).eq("user_id", user_id_str).execute()
        
        target_rank = next_rank
        display_spent = carry_over
        reward_msg = f"🎊 **{next_rank}** に昇格！\n🎁 特典 **{reward:,}枚** を獲得しました！"
    else:
        # 通常更新
        bot.supabase.table("user_coins").update({
            "coin_count": new_coins,
            "monthly_spent": new_spent,
            "weekly_spent": new_weekly
        }).eq("user_id", user_id_str).execute()
        display_spent = new_spent

    # --- 🎭 ロール付け替え処理 (ここから追加) ---
    # サーバーIDを指定（お使いのサーバーIDに書き換えてください）
    GUILD_ID = 1495192303936208906 # 認証済みIDと同じにしていますが、サーバー全体のIDを入れてください
    guild = bot.get_guild(GUILD_ID)
    
    if guild:
        member = guild.get_member(int(user_id))
        if member:
            # 管理対象のランクロールIDリスト
            rank_role_ids = [s["role_id"] for s in RANK_SETTINGS.values() if s["role_id"] is not None]
            
            # 1. 現在のランクに対応するロールIDを取得
            target_role_id = RANK_SETTINGS.get(target_rank, {}).get("role_id")
            
            # 2. 持っているロールの中から、管理対象のランクロールを特定（現在のランク以外を削除対象にする）
            roles_to_remove = [guild.get_role(rid) for rid in rank_role_ids if rid != target_role_id and guild.get_role(rid) in member.roles]
            
            # 不要なロールを削除（Noneを除去）
            if roles_to_remove:
                await member.remove_roles(*[r for r in roles_to_remove if r])
            
            # 3. 新しいランクのロールを付与
            if target_role_id:
                new_role = guild.get_role(target_role_id)
                if new_role and new_role not in member.roles:
                    await member.add_roles(new_role)
    # --- 🎭 ロール処理ここまで ---

    # 3. 画像風のゲージEmbedを作成
    current_goal = RANK_SETTINGS.get(target_rank, {}).get("threshold", 10000)
    percent = min(display_spent / current_goal, 1.0)
    
    if percent >= 0.8:
        color, char, status = 0xff0000, "🟥", "🔥 **激アツ！昇格目前！** 🔥"
    elif percent >= 0.5:
        color, char, status = 0xf1c40f, "🟨", "✨ **チャンス！**"
    else:
        color, char, status = 0x3498db, "🟦", ""

    bar = char * int(10 * percent) + "⬛" * (10 - int(10 * percent))
    
    embed = discord.Embed(title=f"🛡️ 次のレベル: {RANK_SETTINGS.get(target_rank, {}).get('next', 'MAX')}", color=color)
    embed.description = (
        f"**{percent*100:.2f}%** ℹ️\n"
        f"`{bar}`\n\n"
        f"{status}\n"
        f"{reward_msg}"
    )
    
    return embed