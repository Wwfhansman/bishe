import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'core/providers/app_state_provider.dart';
import 'ui/screens/login_page.dart';
import 'ui/screens/home_page.dart'; // We'll create this next

void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppStateProvider()),
      ],
      child: const NiniApp(),
    ),
  );
}

class NiniApp extends StatelessWidget {
  const NiniApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '厨房助理 妮妮',
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blueAccent),
        textTheme: const TextTheme(
          bodyLarge: TextStyle(fontFamily: 'Roboto'),
          bodyMedium: TextStyle(fontFamily: 'Roboto'),
        ),
      ),
      home: Consumer<AppStateProvider>(
        builder: (context, state, child) {
          return state.isAuthenticated ? const HomePage() : const LoginPage();
        },
      ),
    );
  }
}
