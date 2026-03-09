import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/providers/app_state_provider.dart';

class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppStateProvider>();
    
    return Scaffold(
      backgroundColor: const Color(0xFFF6F8FD),
      appBar: AppBar(
        title: const Text('个人中心', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 20)),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
        actions: [
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            onPressed: () {},
          )
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(4),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: Colors.blueAccent, width: 2),
              ),
              child: const CircleAvatar(
                radius: 44,
                backgroundColor: Colors.white,
                child: Icon(Icons.person, size: 48, color: Colors.blueAccent),
              ),
            ),
            const SizedBox(height: 16),
            Text(state.userId ?? 'User', style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
            Container(
              margin: const EdgeInsets.only(top: 8),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(color: Colors.blue.shade50, borderRadius: BorderRadius.circular(12)),
              child: const Text('Lv.5 主厨', style: TextStyle(color: Colors.blueAccent, fontSize: 13, fontWeight: FontWeight.bold)),
            ),
            
            const SizedBox(height: 48),
            
            _buildActionItem(context, Icons.info_outline, '关于我们', onTap: () {}),
            const SizedBox(height: 12),
            _buildActionItem(context, Icons.logout, '退出登录', isDestructive: true, onTap: () {
              showDialog(
                context: context,
                builder: (c) => AlertDialog(
                  title: const Text('退出登录'),
                  content: const Text('确定要退出当前账号吗？'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(c), child: const Text('取消')),
                    TextButton(
                      onPressed: () { 
                        Navigator.pop(c);
                        state.logout();
                      }, 
                      child: const Text('确定', style: TextStyle(color: Colors.redAccent))
                    ),
                  ],
                )
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildActionItem(BuildContext context, IconData icon, String title, {bool isDestructive = false, required VoidCallback onTap}) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.02),
            blurRadius: 10,
            offset: const Offset(0, 4),
          )
        ]
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
        leading: Icon(icon, color: isDestructive ? Colors.redAccent : Colors.black87),
        title: Text(title, style: TextStyle(color: isDestructive ? Colors.redAccent : Colors.black87, fontWeight: FontWeight.w600)),
        trailing: const Icon(Icons.chevron_right, color: Colors.grey),
        onTap: onTap,
      ),
    );
  }
}
